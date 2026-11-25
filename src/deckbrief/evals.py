"""Eval harness skeleton.

Runs the pipeline over a small labelled set of past screens and reports:
- flag recall: share of expected inconsistency/gap flags that were raised
- decision agreement: suggested recommendation vs the investor's labelled decision
- time per screen

The bundled cases are SYNTHETIC (fictional decks written for this repo), so the numbers only
show the harness works. Real use would mean labelling actual past screens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from deckbrief.models import Brief, Mode
from deckbrief.pipeline import screen_sample
from deckbrief.thesis import Thesis

CASES = Path(__file__).resolve().parent / "samples" / "eval_cases.yaml"

# How a recommendation maps onto an investor decision.
REC_TO_DECISION = {
    "advance": "approve",
    "review": "more_info",
    "needs more info": "more_info",
    "pass": "pass",
}


def flag_keys(brief: Brief) -> set[str]:
    """Stable keys for the flags a brief raised, e.g. 'inconsistency:customer count'."""
    keys = {f"gap:{g.criterion_id}" for g in brief.gaps}
    for i in brief.inconsistencies:
        if i.origin == "rule":
            keys.add("inconsistency:" + i.title.split(" differs")[0].lower())
    return keys


@dataclass
class CaseResult:
    case: str
    expected: set[str]
    found: set[str]
    decision: str
    suggested: str | None
    seconds: float

    @property
    def recall(self) -> float:
        return len(self.expected & self.found) / len(self.expected) if self.expected else 1.0


def run_evals(
    thesis: Thesis, mode: Mode = "offline", client: Any = None, model: str | None = None
) -> list[CaseResult]:
    cases = yaml.safe_load(CASES.read_text())["cases"]
    results = []
    for c in cases:
        t0 = time.perf_counter()
        brief = screen_sample(c["sample"], thesis, mode=mode, client=client, model=model)
        took = time.perf_counter() - t0
        rec = brief.score.recommendation if brief.score else None
        suggested = (
            REC_TO_DECISION.get(rec)
            if rec and brief.score and brief.score.total is not None
            else None
        )
        results.append(
            CaseResult(
                case=c["sample"],
                expected=set(c.get("expected_flags", [])),
                found=flag_keys(brief),
                decision=c["decision"],
                suggested=suggested,
                seconds=round(took, 2),
            )
        )
    return results


def summarise(results: list[CaseResult]) -> dict[str, Any]:
    expected = sum(len(r.expected) for r in results)
    hit = sum(len(r.expected & r.found) for r in results)
    decided = [r for r in results if r.suggested is not None]
    return {
        "cases": len(results),
        "flag_recall": round(hit / expected, 2) if expected else None,
        "decision_agreement": (
            round(sum(r.suggested == r.decision for r in decided) / len(decided), 2)
            if decided
            else None
        ),
        "decisions_compared": len(decided),
        "mean_seconds": round(sum(r.seconds for r in results) / len(results), 2)
        if results
        else 0.0,
    }
