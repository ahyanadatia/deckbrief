"""Generate the fictional sample decks and website snapshots used by the demo and the evals.

None of these companies exist. Every number is made up, and some are deliberately
inconsistent so the checks have something to find. Needs reportlab (in the dev extras):

    python scripts/make_sample_decks.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent / "src" / "deckbrief" / "samples"
INK = HexColor("#111827")
ACCENT = HexColor("#166534")
GREY = HexColor("#6b7280")

Slides = list[tuple[str, list[str]]]

COMPANIES: dict[str, dict[str, object]] = {
    "gridline": {
        "name": "Gridline Analytics",
        # Planted issues: ARR differs between p.3 and p.4, customer count differs between
        # p.3 and p.6, founding year and headcount differ from the website, and there is
        # no competition slide.
        "slides": [
            (
                "Gridline Analytics",
                [
                    "Series B investor presentation, October 2026",
                    "Congestion forecasting for electricity distribution networks",
                ],
            ),
            (
                "The problem",
                [
                    "Low-voltage networks are running out of headroom as heat pumps,",
                    "EV chargers and rooftop solar connect. Connections wait months.",
                    "Gridline forecasts congestion 15 minutes ahead from smart-meter and",
                    "substation data, so operators can connect more low-carbon load now.",
                ],
            ),
            (
                "Traction",
                [
                    "ARR of GBP 4.2m in September 2026, up from GBP 1.6m a year earlier",
                    "6 grid operator customers across the UK and the Netherlands",
                    "Net revenue retention of 135%",
                    "Annual licence per network area, typically 3-year contracts",
                ],
            ),
            (
                "Financials",
                [
                    "ARR (September 2026): GBP 3.8m",
                    "Gross margin: 78%",
                    "EBITDA (FY2025): -GBP 2.4m",
                    "Runway: 20 months at current burn",
                ],
            ),
            (
                "Impact",
                [
                    "61,000 extra heat pump and EV connections enabled since launch",
                    "Estimated 95,000 tCO2e avoided per year",
                    "(company methodology, not independently reviewed)",
                ],
            ),
            (
                "Team and raise",
                [
                    "Founded in 2017 in London by power-systems engineers",
                    "52 employees across London and Rotterdam",
                    "4 grid operator customers on multi-year contracts",
                    "Raising GBP 25m Series B to expand into Germany",
                ],
            ),
        ],
        "site": {
            "https://gridline.example/": (
                "Gridline Analytics - congestion forecasting for grids",
                "<h1>Connect more low-carbon tech to the grid you already have</h1>"
                "<p>Gridline helps distribution network operators find headroom on "
                "low-voltage networks. We work with 4 grid operator customers in the UK and "
                "the Netherlands.</p><a href='/about'>About us</a> <a href='/impact'>Impact</a>",
            ),
            "https://gridline.example/about": (
                "About Gridline",
                "<h1>About</h1><p>Gridline was founded in 2019 by two power-systems engineers "
                "who met at a network operator. Today we are a team of 48 employees in London and Rotterdam.</p>",
            ),
            "https://gridline.example/impact": (
                "Impact",
                "<h1>Impact</h1><p>Every connection we unlock is a heat pump or EV charger that "
                "replaces a gas boiler or a petrol car. We estimate 95,000 tCO2e avoided per "
                "year using our own methodology.</p>",
            ),
        },
    },
    "brightloop": {
        "name": "Brightloop Storage",
        # A tidy, consistent deck: used as a control in the evals.
        "slides": [
            (
                "Brightloop Storage",
                ["Series B, 2026", "Second-life EV batteries for commercial sites"],
            ),
            (
                "Product",
                [
                    "Containerised storage built from retired EV battery packs",
                    "Cuts peak demand charges and lets sites run on more on-site solar",
                ],
            ),
            (
                "Traction",
                [
                    "ARR of GBP 6.1m in June 2026, up from GBP 3.0m a year earlier",
                    "38 commercial customers including logistics and cold-storage sites",
                    "Gross margin: 41% on hardware, 72% on software",
                    "CAC payback of 14 months",
                ],
            ),
            (
                "Competition",
                [
                    "Competitors: new-cell storage integrators and diesel peakers",
                    "We are differentiated on price per kWh from reusing packs",
                ],
            ),
            (
                "Impact",
                [
                    "Estimated 21,000 tCO2e avoided per year (third-party reviewed, 2026)",
                    "Each site extends battery life by 8-10 years before recycling",
                ],
            ),
            (
                "Team and raise",
                [
                    "Founded in 2020 by former automotive battery engineers",
                    "64 employees",
                    "Raising GBP 30m; use of funds: manufacturing scale-up and EU sales",
                ],
            ),
        ],
        "site": {
            "https://brightloop.example/": (
                "Brightloop Storage",
                "<h1>Batteries get a second life</h1><p>Founded in 2020. 38 commercial "
                "customers. A team of 64 employees.</p>",
            ),
        },
    },
    "verdant": {
        "name": "Verdant Ledger",
        # Planted issues: customer count differs between slides; no gross margin, CAC or
        # retention; no raise or runway details.
        "slides": [
            (
                "Verdant Ledger",
                ["Seed extension, 2026", "Carbon accounting for mid-sized manufacturers"],
            ),
            (
                "Traction",
                [
                    "ARR of GBP 0.9m in August 2026",
                    "120 customers across food and drink manufacturing",
                ],
            ),
            (
                "Why us",
                [
                    "Competitors are built for large enterprises and consultancies",
                    "We automate Scope 1 and 2 reporting from utility bills",
                ],
            ),
            (
                "Customers",
                [
                    "85 customers live on the platform",
                    "Typical contract: GBP 7k per year",
                ],
            ),
            ("Team", ["Founded in 2022", "14 employees"]),
        ],
        "site": {
            "https://verdant.example/": (
                "Verdant Ledger",
                "<h1>Carbon accounting that does itself</h1><p>Trusted by manufacturers "
                "measuring their carbon emissions.</p>",
            ),
        },
    },
}

FOOTER = "FICTIONAL SAMPLE - {name} is not a real company. All figures are invented."


def write_deck(slug: str, name: str, slides: Slides) -> Path:
    out = ROOT / slug / "deck.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = landscape(A4)
    c = canvas.Canvas(str(out), pagesize=(w, h), invariant=1)
    c.setTitle(f"{name} - fictional sample deck")
    for i, (title, lines) in enumerate(slides, start=1):
        c.setFillColor(ACCENT)
        c.rect(0, h - 12, w, 12, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(60, h - 100, title)
        c.setFillColor(INK)
        c.setFont("Helvetica", 17)
        y = h - 170
        for line in lines:
            c.drawString(60, y, line)
            y -= 34
        c.setFillColor(GREY)
        c.setFont("Helvetica", 10)
        c.drawString(60, 30, FOOTER.format(name=name))
        c.drawRightString(w - 60, 30, str(i))
        c.showPage()
    c.save()
    return out


def write_site(slug: str, pages: dict[str, tuple[str, str]]) -> None:
    import json

    site = ROOT / slug / "site.json"
    payload = {
        url: f"<html><head><title>{title}</title></head><body>{body}</body></html>"
        for url, (title, body) in pages.items()
    }
    site.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    for slug, spec in COMPANIES.items():
        name = str(spec["name"])
        path = write_deck(slug, name, spec["slides"])  # type: ignore[arg-type]
        write_site(slug, spec["site"])  # type: ignore[arg-type]
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
