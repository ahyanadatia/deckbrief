"""Data models shared by the pipeline, the agent, storage and the UI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["offline", "scripted", "live"]
Severity = Literal["low", "medium", "high"]
Recommendation = Literal["advance", "review", "pass", "needs more info"]
Decision = Literal["approve", "pass", "more_info"]


class Source(BaseModel):
    """One citable piece of evidence: a deck page or a fetched web page."""

    id: str  # "deck p.3" or the page URL
    kind: Literal["deck", "web"]
    label: str
    text: str
    url: str | None = None
    page: int | None = None


class Figure(BaseModel):
    """A number pulled out of a source by regex (not by the LLM)."""

    metric: str
    value: float
    period: str | None
    raw: str
    source_id: str


class Inconsistency(BaseModel):
    title: str
    detail: str
    source_ids: list[str]
    severity: Severity = "medium"
    origin: Literal["rule", "agent"] = "rule"


class Gap(BaseModel):
    criterion_id: str
    label: str
    reason: str
    questions: list[str]


class Metric(BaseModel):
    """A financial or operating metric as reported by the company."""

    name: str
    value: str
    period: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class Competitor(BaseModel):
    name: str
    note: str
    source_ids: list[str] = Field(default_factory=list)


IMPACT_DIMENSIONS = ("what", "who", "how_much", "contribution", "risk")


class ImpactDimension(BaseModel):
    """One of the Five Dimensions of impact. Empty `source_ids` means unevidenced."""

    dimension: Literal["what", "who", "how_much", "contribution", "risk"]
    assessment: str
    source_ids: list[str] = Field(default_factory=list)


class ClimateImpact(BaseModel):
    mechanism: str
    abatement_logic: str
    evidenced: bool = False
    source_ids: list[str] = Field(default_factory=list)
    dimensions: list[ImpactDimension] = Field(default_factory=list)
    suggested_kpis: list[str] = Field(default_factory=list)
    missing_kpis: list[str] = Field(default_factory=list)


class Rating(BaseModel):
    criterion_id: str
    score: int = Field(ge=0, le=5)
    rationale: str
    source_ids: list[str] = Field(default_factory=list)


class CriterionScore(BaseModel):
    criterion_id: str
    label: str
    weight: float
    score: int | None
    rationale: str
    source_ids: list[str] = Field(default_factory=list)


class Score(BaseModel):
    total: float | None
    coverage: float
    recommendation: Recommendation
    criteria: list[CriterionScore]


class Brief(BaseModel):
    id: str
    company: str
    created_at: datetime
    mode: Mode
    model: str | None = None
    thesis_name: str
    one_liner: str | None = None
    sources: list[Source]
    figures: list[Figure] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    competitive_summary: str | None = None
    competitors: list[Competitor] = Field(default_factory=list)
    climate: ClimateImpact | None = None
    inconsistencies: list[Inconsistency] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    score: Score | None = None
    warnings: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    elapsed_s: float = 0.0

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)
