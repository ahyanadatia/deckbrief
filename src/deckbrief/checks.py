"""Deterministic checks that run with or without an API key.

1. `extract_figures` pulls numbers out of every source with regexes.
2. `find_inconsistencies` compares the same metric across sources (deck pages and website).
3. `find_gaps` lists thesis criteria with no supporting evidence at all.

These are deliberately simple. They miss things a human would catch, but they never
hallucinate, and a persuasive deck can't talk them out of a mismatch.
"""

from __future__ import annotations

import re
from collections import defaultdict

from deckbrief.models import Figure, Gap, Inconsistency, Severity, Source
from deckbrief.thesis import Thesis

MONEY = r"(?:GBP|EUR|USD|£|€|\$)\s?(-?[\d.,]+)\s?(bn|m|k|million)?\b"
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
PERIOD_RE = re.compile(rf"\b((?:{MONTHS})\s+20\d\d|FY\s?20\d\d|Q[1-4]\s+20\d\d)\b", re.I)
SCALE = {"bn": 1e9, "m": 1e6, "million": 1e6, "k": 1e3, None: 1.0}

COUNT_PATTERNS: dict[str, re.Pattern[str]] = {
    "customers": re.compile(r"\b(\d[\d,]*)\s+(?:[A-Za-z-]+\s+){0,3}?(?:customers|clients)\b", re.I),
    "employees": re.compile(
        r"\b(?:team of\s+)?(\d[\d,]*)\s+(?:employees|staff|people|FTEs?)\b", re.I
    ),
}
FOUNDED_RE = re.compile(r"\b(?:founded|established|started)\b\D{0,20}((?:19|20)\d{2})", re.I)
PERCENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "gross margin": re.compile(r"gross margin\D{0,15}(\d+(?:\.\d+)?)\s?%", re.I),
    "net revenue retention": re.compile(
        r"(?:net revenue retention|NRR)\D{0,15}(\d+(?:\.\d+)?)\s?%", re.I
    ),
}
TCO2E_RE = re.compile(r"\b(\d[\d,]*)\s?tCO2e\b", re.I)

LABELS = {
    "arr": "ARR",
    "revenue": "Revenue",
    "customers": "Customer count",
    "employees": "Headcount",
    "founded": "Founding year",
    "gross margin": "Gross margin",
    "net revenue retention": "Net revenue retention",
    "tco2e": "Emissions avoided (tCO2e/yr)",
}


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _period(line: str) -> str | None:
    m = PERIOD_RE.search(line)
    return " ".join(m.group(1).split()).title().replace("Fy", "FY") if m else None


def _money(m: re.Match[str]) -> float:
    return _num(m.group(1)) * SCALE[(m.group(2) or "").lower() or None]


def _line_figures(line: str) -> list[tuple[str, float, str | None]]:
    """All (metric, value, period) figures found in one line of text."""
    found: list[tuple[str, float, str | None]] = []
    money = re.search(MONEY, line, re.I)
    if money and re.search(r"\bARR\b|annual recurring revenue", line, re.I):
        found.append(("arr", _money(money), _period(line)))
    elif (
        money
        and re.search(r"\b(revenue|turnover)\b", line, re.I)
        and not re.search(r"retention", line, re.I)
    ):
        found.append(("revenue", _money(money), _period(line)))
    for metric, pat in COUNT_PATTERNS.items():
        found += [(metric, _num(m.group(1)), None) for m in pat.finditer(line)]
    if m := FOUNDED_RE.search(line):
        found.append(("founded", float(m.group(1)), None))
    for metric, pat in PERCENT_PATTERNS.items():
        if m := pat.search(line):
            found.append((metric, float(m.group(1)), None))
    if m := TCO2E_RE.search(line):
        found.append(("tco2e", _num(m.group(1)), None))
    return found


def extract_figures(sources: list[Source]) -> list[Figure]:
    out: list[Figure] = []
    for src in sources:
        for raw in src.text.splitlines():
            line = raw.strip()
            if not line or len(line) > 300:
                continue
            for metric, value, period in _line_figures(line):
                out.append(
                    Figure(metric=metric, value=value, period=period, raw=line, source_id=src.id)
                )
    return out


def format_value(metric: str, value: float) -> str:
    if metric in {"arr", "revenue"}:
        return f"{value / 1e6:.1f}m" if abs(value) >= 1e5 else f"{value:,.0f}"
    if metric in PERCENT_PATTERNS:
        return f"{value:g}%"
    if metric == "founded":
        return str(int(value))
    return f"{value:,.0f}"


def _differs(a: float, b: float, tolerance: float) -> bool:
    if a == b:
        return False
    return abs(a - b) / max(abs(a), abs(b)) > tolerance


SEVERITY: dict[str, Severity] = {"arr": "high", "revenue": "high", "customers": "high"}


def find_inconsistencies(figures: list[Figure], tolerance: float = 0.02) -> list[Inconsistency]:
    """Flag a metric reported with different values in different places.

    Money figures are only compared within the same stated period (an ARR figure for
    September 2026 is not compared with one from a year earlier). Counts and founding year are
    compared regardless of period, which can cause false positives when a deck mixes dates.
    """
    groups: dict[tuple[str, str], list[Figure]] = defaultdict(list)
    for f in figures:
        key_period = (f.period or "") if f.metric in {"arr", "revenue"} else ""
        groups[(f.metric, key_period)].append(f)

    flags: list[Inconsistency] = []
    for (metric, period), figs in groups.items():
        # One value per source; the first mention on a page wins.
        by_source: dict[str, Figure] = {}
        for f in figs:
            by_source.setdefault(f.source_id, f)
        distinct = list(by_source.values())
        if len(distinct) < 2:
            continue
        tol = 0.0 if metric == "founded" else tolerance
        if not any(_differs(a.value, b.value, tol) for a in distinct for b in distinct):
            continue
        label = LABELS.get(metric, metric)
        where = "; ".join(f"{format_value(metric, f.value)} on {f.source_id}" for f in distinct)
        flags.append(
            Inconsistency(
                title=f"{label} differs between sources" + (f" ({period})" if period else ""),
                detail=f"Reported as {where}.",
                source_ids=[f.source_id for f in distinct],
                severity=SEVERITY.get(metric, "medium"),
                origin="rule",
            )
        )
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(flags, key=lambda i: order[i.severity])


def evidence_for(thesis: Thesis, sources: list[Source]) -> dict[str, list[str]]:
    """Map each criterion id to the source ids that mention any of its keywords."""
    hits: dict[str, list[str]] = {}
    for c in thesis.criteria:
        kws = [k.lower() for k in c.evidence_keywords]
        hits[c.id] = [s.id for s in sources if any(k in s.text.lower() for k in kws)]
    return hits


def find_gaps(thesis: Thesis, sources: list[Source]) -> list[Gap]:
    gaps: list[Gap] = []
    for c in thesis.criteria:
        if not evidence_for(thesis, sources)[c.id]:
            gaps.append(
                Gap(
                    criterion_id=c.id,
                    label=c.label,
                    reason="Nothing in the deck or website addresses this criterion.",
                    questions=c.questions,
                )
            )
    return gaps
