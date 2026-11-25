"""Turns per-criterion ratings into a weighted score and a recommendation.

The model only rates individual criteria (0-5, with citations). The arithmetic and the
thresholds live here, so the final number is reproducible and easy to argue with.
"""

from __future__ import annotations

from deckbrief.models import CriterionScore, Gap, Rating, Recommendation, Score
from deckbrief.thesis import Thesis


def score(thesis: Thesis, ratings: list[Rating], gaps: list[Gap]) -> Score:
    by_id = {r.criterion_id: r for r in ratings}
    gap_ids = {g.criterion_id for g in gaps}
    rows: list[CriterionScore] = []
    for c in thesis.criteria:
        r = by_id.get(c.id)
        if r is None or c.id in gap_ids or not r.source_ids:
            # A rating with no valid citation doesn't count: it becomes a diligence gap.
            rows.append(
                CriterionScore(
                    criterion_id=c.id,
                    label=c.label,
                    weight=c.weight,
                    score=None,
                    rationale="No cited evidence." if r is None else f"Not counted: {r.rationale}",
                )
            )
            continue
        rows.append(
            CriterionScore(
                criterion_id=c.id,
                label=c.label,
                weight=c.weight,
                score=r.score,
                rationale=r.rationale,
                source_ids=r.source_ids,
            )
        )

    total_w = sum(r.weight for r in rows)
    rated = [r for r in rows if r.score is not None]
    rated_w = sum(r.weight for r in rated)
    coverage = rated_w / total_w if total_w else 0.0
    total = sum(r.weight * (r.score or 0) for r in rated) / rated_w / 5 * 100 if rated_w else None

    rec: Recommendation
    if total is None or coverage < thesis.min_coverage:
        rec = "needs more info"
    elif total >= thesis.thresholds.advance:
        rec = "advance"
    elif total >= thesis.thresholds.review:
        rec = "review"
    else:
        rec = "pass"
    return Score(
        total=round(total, 1) if total is not None else None,
        coverage=round(coverage, 2),
        recommendation=rec,
        criteria=rows,
    )
