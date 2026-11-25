"""One screening, start to finish: deck + website -> checks -> (agent) -> scored brief."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from deckbrief.agent import BriefAgent, Submission, clean_submission, submission_from_json
from deckbrief.checks import extract_figures, find_gaps, find_inconsistencies
from deckbrief.deck import read_deck
from deckbrief.models import IMPACT_DIMENSIONS, Brief, Gap, Inconsistency, Mode
from deckbrief.scoring import score
from deckbrief.thesis import Thesis
from deckbrief.web_sources import Fetcher, SafeFetcher, SnapshotFetcher, fetch_website

SAMPLES = Path(__file__).resolve().parent / "samples"
SAMPLE_WEBSITES = {
    "gridline": "https://gridline.example/",
    "brightloop": "https://brightloop.example/",
    "verdant": "https://verdant.example/",
}

IMPACT_QUESTIONS = {
    "what": "What outcome does the product change, and for which emissions source?",
    "who": "Who experiences the outcome (customers, grid users, communities)?",
    "how_much": "How big is the effect per customer, and how is it measured?",
    "contribution": "What would have happened without the product (the counterfactual)?",
    "risk": "What could make the impact smaller than claimed, and what are the adverse impacts?",
}

Emit = Callable[[str], None]


def sample_paths(slug: str) -> tuple[Path, str, Path]:
    """Return (deck pdf, website url, website snapshot) for a bundled fictional sample."""
    folder = SAMPLES / slug
    if not (folder / "deck.pdf").exists():
        raise ValueError(f"unknown sample: {slug}")
    return folder / "deck.pdf", SAMPLE_WEBSITES[slug], folder / "site.json"


def _merge_flags(rule: list[Inconsistency], agent: list[Inconsistency]) -> list[Inconsistency]:
    """Keep agent flags unless a rule flag already covers exactly the same sources."""
    covered = [set(r.source_ids) for r in rule]
    return rule + [a for a in agent if not any(set(a.source_ids) <= c for c in covered)]


def screen(
    deck: Path,
    thesis: Thesis,
    *,
    website: str | None = None,
    mode: Literal["offline", "scripted", "live"] = "offline",
    fetcher: Fetcher | None = None,
    client: Any = None,
    model: str | None = None,
    scripted: Path | None = None,
    emit: Emit | None = None,
) -> Brief:
    started = time.perf_counter()
    trace: list[str] = []

    def log(msg: str) -> None:
        trace.append(msg)
        if emit:
            emit(msg)

    log(f"Reading {deck.name}")
    sources = read_deck(deck)
    log(f"Extracted text from {len(sources)} deck pages")
    warnings: list[str] = []
    if website:
        log(f"Fetching website {website}")
        web, w = fetch_website(fetcher or SafeFetcher(), website)
        sources += web
        warnings += w
        log(f"Got {len(web)} website pages")

    figures = extract_figures(sources)
    rule_flags = find_inconsistencies(figures)
    gaps = find_gaps(thesis, sources)
    log(f"Rule checks: {len(figures)} figures, {len(rule_flags)} inconsistencies, {len(gaps)} gaps")

    company = sources[0].text.splitlines()[0][:80]
    brief = Brief(
        id=uuid.uuid4().hex[:10],
        company=company,
        created_at=datetime.now(UTC),
        mode=mode,
        thesis_name=thesis.name,
        sources=sources,
        figures=figures,
        inconsistencies=rule_flags,
        gaps=gaps,
        warnings=warnings,
    )

    sub: Submission | None = None
    if mode == "live":
        if client is None or not model:
            raise ValueError("live mode needs an Anthropic client and a model name")
        log(f"Running the agent ({model})")
        agent = BriefAgent(client, model, fetcher=fetcher or SafeFetcher(), emit=log)
        out = agent.run(thesis, sources, website)
        brief.sources = out.sources
        brief.model = model
        warnings += out.log
        sub = out.submission
        if sub is None:
            warnings.append("The agent did not return a valid brief; showing rule checks only.")
    elif mode == "scripted":
        if scripted is None:
            raise ValueError("scripted mode needs a saved submission")
        log("Loading the scripted sample output (not a live model call)")
        sub = submission_from_json(scripted.read_text())

    if sub is not None:
        known = {s.id for s in brief.sources}
        sub, agent_flags, unverified, w = clean_submission(sub, known, thesis)
        warnings += w
        brief.one_liner = sub.one_liner
        brief.metrics = sub.metrics
        brief.competitive_summary = sub.competitive_summary
        brief.competitors = sub.competitors
        brief.climate = sub.climate
        brief.inconsistencies = _merge_flags(rule_flags, agent_flags)
        brief.unverified = unverified
        brief.questions = sub.questions
        gap_ids = {g.criterion_id for g in gaps}
        for r in sub.ratings:
            c = thesis.criterion(r.criterion_id)
            if c and not r.source_ids and r.criterion_id not in gap_ids:
                gaps.append(
                    Gap(
                        criterion_id=c.id,
                        label=c.label,
                        reason="The model rated this without citing any evidence.",
                        questions=c.questions,
                    )
                )
        have = {d.dimension for d in sub.climate.dimensions if d.source_ids}
        for dim in IMPACT_DIMENSIONS:
            if dim not in have:
                gaps.append(
                    Gap(
                        criterion_id=f"impact:{dim}",
                        label=f"Impact - {dim.replace('_', ' ')}",
                        reason="Not evidenced in the deck or website.",
                        questions=[IMPACT_QUESTIONS[dim]],
                    )
                )
        brief.gaps = gaps
        brief.score = score(thesis, sub.ratings, gaps)
        log(f"Scored in code: {brief.score.total} ({brief.score.recommendation})")
    else:
        brief.score = score(thesis, [], gaps)

    brief.warnings = warnings
    brief.trace = trace
    brief.elapsed_s = round(time.perf_counter() - started, 2)
    return brief


def screen_sample(
    slug: str,
    thesis: Thesis,
    *,
    mode: Mode = "scripted",
    client: Any = None,
    model: str | None = None,
    emit: Emit | None = None,
) -> Brief:
    deck, url, snapshot = sample_paths(slug)
    scripted = SAMPLES / slug / "scripted_brief.json"
    if mode == "scripted" and not scripted.exists():
        mode = "offline"
    return screen(
        deck,
        thesis,
        website=url,
        mode=mode,
        fetcher=SnapshotFetcher(snapshot),
        client=client,
        model=model,
        scripted=scripted,
        emit=emit,
    )
