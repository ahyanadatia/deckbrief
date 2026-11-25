from __future__ import annotations

from pathlib import Path

import pytest

from deckbrief.checks import extract_figures, find_gaps, find_inconsistencies
from deckbrief.deck import DeckError, read_deck
from deckbrief.models import Source
from deckbrief.pipeline import sample_paths


def src(sid: str, text: str) -> Source:
    return Source(id=sid, kind="deck", label=sid, text=text)


def test_reads_deck_pages_with_page_ids() -> None:
    pages = read_deck(sample_paths("gridline")[0])
    assert [p.id for p in pages] == [f"deck p.{i}" for i in range(1, 7)]
    assert "ARR of GBP 4.2m" in pages[2].text


def test_rejects_non_pdf(tmp_path: Path) -> None:
    bad = tmp_path / "deck.pdf"
    bad.write_text("not a pdf")
    with pytest.raises(DeckError):
        read_deck(bad)


def test_extracts_money_with_period_and_counts() -> None:
    figs = extract_figures(
        [
            src(
                "deck p.1",
                "ARR (September 2026): GBP 3.8m\n6 grid operator customers\nA team of 48 employees",
            )
        ]
    )
    by = {f.metric: f for f in figs}
    assert by["arr"].value == 3_800_000 and by["arr"].period == "September 2026"
    assert by["customers"].value == 6
    assert by["employees"].value == 48


def test_flags_conflicting_figures_across_slides() -> None:
    figs = extract_figures(
        [
            src("deck p.3", "ARR of GBP 4.2m in September 2026\n6 grid operator customers"),
            src("deck p.4", "ARR (September 2026): GBP 3.8m"),
            src("deck p.6", "4 grid operator customers"),
        ]
    )
    titles = [i.title for i in find_inconsistencies(figs)]
    assert any(t.startswith("ARR differs") for t in titles)
    assert any(t.startswith("Customer count differs") for t in titles)


def test_money_in_different_periods_is_not_a_conflict() -> None:
    figs = extract_figures(
        [
            src("deck p.2", "ARR of GBP 4.2m in September 2026"),
            src("deck p.3", "ARR of GBP 1.6m in September 2025"),
        ]
    )
    assert find_inconsistencies(figs) == []


def test_same_values_are_not_flagged() -> None:
    figs = extract_figures(
        [src("deck p.1", "Founded in 2020"), src("https://x.example/", "Founded in 2020")]
    )
    assert find_inconsistencies(figs) == []


def test_gaps_list_criteria_without_evidence(thesis) -> None:  # type: ignore[no-untyped-def]
    gaps = find_gaps(
        thesis,
        [
            src(
                "deck p.1",
                "ARR of GBP 5m, gross margin 70%, founder-led team, raising a Series B, 2,000 tCO2e avoided",
            )
        ],
    )
    assert [g.criterion_id for g in gaps] == ["competitive_position"]
    assert gaps[0].questions
