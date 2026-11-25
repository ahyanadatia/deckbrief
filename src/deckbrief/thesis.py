"""Investment thesis loaded from YAML (see theses/climate_growth.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_THESIS = Path(__file__).resolve().parent / "theses" / "climate_growth.yaml"


class Criterion(BaseModel):
    id: str
    label: str
    weight: float = Field(gt=0)
    guidance: str
    evidence_keywords: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class Thresholds(BaseModel):
    advance: float = 70
    review: float = 50


class Thesis(BaseModel):
    name: str
    description: str = ""
    thresholds: Thresholds = Thresholds()
    min_coverage: float = 0.6
    impact_kpis: list[str] = Field(default_factory=list)
    criteria: list[Criterion]

    def criterion(self, cid: str) -> Criterion | None:
        return next((c for c in self.criteria if c.id == cid), None)

    def prompt_block(self) -> str:
        lines = [f"Investment thesis: {self.name}", self.description.strip(), "Criteria:"]
        for c in self.criteria:
            lines.append(f"- {c.id} ({c.label}, weight {c.weight:g}): {c.guidance}")
        return "\n".join(lines)


def load_thesis(path: Path | None = None) -> Thesis:
    data = yaml.safe_load((path or DEFAULT_THESIS).read_text())
    return Thesis.model_validate(data)
