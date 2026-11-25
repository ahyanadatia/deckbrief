from __future__ import annotations

import json

from conftest import Block, FakeClient, Resp

from deckbrief.agent import BriefAgent, clean_submission, submission_from_json
from deckbrief.models import Rating, Source
from deckbrief.pipeline import SAMPLES
from deckbrief.scoring import score
from deckbrief.web_sources import SnapshotFetcher


def test_score_is_weighted_and_ignores_uncited_ratings(thesis) -> None:  # type: ignore[no-untyped-def]
    ratings = [
        Rating(criterion_id=c.id, score=4, rationale="ok", source_ids=["deck p.1"])
        for c in thesis.criteria
    ]
    ratings[0] = Rating(criterion_id="climate_impact", score=0, rationale="vibes", source_ids=[])
    s = score(thesis, ratings, gaps=[])
    assert s.criteria[0].score is None  # uncited rating does not count
    assert s.total == 80.0
    assert s.coverage == round(9 / 12, 2)
    assert s.recommendation == "advance"


def test_low_coverage_means_needs_more_info(thesis) -> None:  # type: ignore[no-untyped-def]
    s = score(
        thesis, [Rating(criterion_id="team", score=5, rationale="x", source_ids=["deck p.1"])], []
    )
    assert s.recommendation == "needs more info"


def test_clean_submission_drops_unknown_citations(thesis) -> None:  # type: ignore[no-untyped-def]
    sub = submission_from_json((SAMPLES / "gridline" / "scripted_brief.json").read_text())
    sub.metrics[0].source_ids = ["deck p.99"]
    cleaned, flags, unverified, warnings = clean_submission(
        sub, {"deck p.3", "deck p.4", "deck p.5"}, thesis
    )
    assert "ARR: GBP 4.2m" in unverified
    assert any("deck p.99" in w for w in warnings)
    assert all(set(f.source_ids) <= {"deck p.3", "deck p.4", "deck p.5"} for f in flags)


def _submit_input() -> dict[str, object]:
    data: dict[str, object] = json.loads((SAMPLES / "gridline" / "scripted_brief.json").read_text())
    data.pop("_note")
    return data


def test_agent_loop_fetches_then_submits(thesis) -> None:  # type: ignore[no-untyped-def]
    client = FakeClient(
        [
            Resp(
                [
                    Block(
                        "tool_use",
                        id="t1",
                        name="fetch_company_page",
                        input={"url": "https://evil.example/x"},
                    ),
                    Block(
                        "tool_use",
                        id="t2",
                        name="fetch_company_page",
                        input={"url": "https://gridline.example/about"},
                    ),
                ]
            ),
            Resp(
                [
                    Block(
                        "tool_use",
                        id="t3",
                        name="submit_brief",
                        input={"one_liner": "missing fields"},
                    )
                ]
            ),
            Resp([Block("tool_use", id="t4", name="submit_brief", input=_submit_input())]),
        ]
    )
    fetcher = SnapshotFetcher(SAMPLES / "gridline" / "site.json")
    deck = [Source(id="deck p.1", kind="deck", label="p1", text="Gridline")]
    out = BriefAgent(client, "test-model", fetcher=fetcher).run(
        thesis, deck, "https://gridline.example/"
    )
    assert out.submission is not None
    assert "https://gridline.example/about" in {s.id for s in out.sources}
    results = client.messages.calls[1]["messages"][-1]["content"]
    assert results[0]["is_error"] and "own website" in results[0]["content"]
    # the invalid submission was bounced back as a tool error
    assert client.messages.calls[2]["messages"][-1]["content"][0]["is_error"]
    assert "<untrusted" in client.messages.calls[0]["messages"][0]["content"]
