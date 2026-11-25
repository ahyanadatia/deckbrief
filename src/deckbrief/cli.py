"""Command line: screen a deck, run the sample, record decisions, run evals, serve the UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from deckbrief.config import Settings, load_settings
from deckbrief.models import Brief, Mode
from deckbrief.pipeline import screen, screen_sample
from deckbrief.store import Store
from deckbrief.thesis import load_thesis

app = typer.Typer(add_completion=False, help="First-pass pitch-deck screening.")
ThesisOpt = Annotated[
    Path | None, typer.Option(help="Thesis YAML (defaults to the bundled example)")
]


def _client(settings: Settings, live: bool) -> Any:
    if not live:
        return None
    if not settings.has_key:
        raise typer.BadParameter("--live needs ANTHROPIC_API_KEY (see .env.example)")
    import anthropic

    return anthropic.Anthropic(api_key=settings.api_key)


def _print(brief: Brief) -> None:
    s = brief.score
    typer.echo(f"\n{brief.company}  [{brief.mode}]  {brief.elapsed_s}s")
    if s:
        total = "-" if s.total is None else f"{s.total}"
        typer.echo(f"Score {total}/100, coverage {s.coverage:.0%}, suggestion: {s.recommendation}")
    typer.echo(f"\nInconsistencies ({len(brief.inconsistencies)}):")
    for i in brief.inconsistencies:
        typer.echo(f"  [{i.severity}/{i.origin}] {i.title}: {i.detail} ({', '.join(i.source_ids)})")
    typer.echo(f"\nDiligence gaps ({len(brief.gaps)}):")
    for g in brief.gaps:
        typer.echo(f"  {g.label}: {g.questions[0] if g.questions else g.reason}")
    if brief.metrics:
        typer.echo("\nCompany-reported metrics:")
        for m in brief.metrics:
            typer.echo(f"  {m.name}: {m.value} {m.period or ''} ({', '.join(m.source_ids)})")
    for w in brief.warnings:
        typer.echo(f"warning: {w}")
    typer.echo(f"\nSaved as {brief.id}")


@app.command("screen")
def screen_cmd(
    deck: Path,
    website: Annotated[str | None, typer.Option(help="Company website URL")] = None,
    live: Annotated[bool, typer.Option(help="Run the Claude agent (needs a key)")] = False,
    thesis: ThesisOpt = None,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Also write the brief as JSON")
    ] = None,
) -> None:
    """Screen a pitch-deck PDF."""
    settings = load_settings()
    brief = screen(
        deck,
        load_thesis(thesis),
        website=website,
        mode="live" if live else "offline",
        client=_client(settings, live),
        model=settings.model,
        emit=lambda m: typer.echo(f"- {m}"),
    )
    Store(settings.data_dir / "deckbrief.db").save(brief)
    if json_out:
        json_out.write_text(brief.model_dump_json(indent=2))
    _print(brief)


@app.command()
def sample(
    live: Annotated[
        bool, typer.Option(help="Use the real agent instead of the scripted brief")
    ] = False,
    offline: Annotated[bool, typer.Option(help="Rule checks only")] = False,
    name: Annotated[str, typer.Option(help="gridline, brightloop or verdant")] = "gridline",
) -> None:
    """Screen a bundled fictional sample deck."""
    settings = load_settings()
    mode: Mode = "live" if live else "offline" if offline else "scripted"
    brief = screen_sample(
        name,
        load_thesis(),
        mode=mode,
        client=_client(settings, live),
        model=settings.model,
        emit=lambda m: typer.echo(f"- {m}"),
    )
    Store(settings.data_dir / "deckbrief.db").save(brief)
    _print(brief)


@app.command()
def decide(
    brief_id: str,
    decision: Annotated[str, typer.Argument(help="approve, pass or more_info")],
    notes: Annotated[str, typer.Option()] = "",
) -> None:
    """Record an investor decision on a brief."""
    if decision not in {"approve", "pass", "more_info"}:
        raise typer.BadParameter("decision must be approve, pass or more_info")
    Store(load_settings().data_dir / "deckbrief.db").decide(brief_id, decision, notes)  # type: ignore[arg-type]
    typer.echo("saved")


@app.command()
def history(csv: Annotated[bool, typer.Option(help="Print as CSV")] = False) -> None:
    """List screens and their latest decision."""
    store = Store(load_settings().data_dir / "deckbrief.db")
    if csv:
        typer.echo(store.export_csv(), nl=False)
        return
    for r in store.history():
        typer.echo(
            f"{r['id']}  {r['company'][:28]:28}  {r['mode']:8}  {r['recommendation'] or '':16}  {r['decision'] or '-'}"
        )


@app.command("eval")
def eval_cmd(
    live: Annotated[bool, typer.Option(help="Use the real agent (costs API calls)")] = False,
) -> None:
    """Run the eval skeleton on the synthetic labelled cases."""
    from deckbrief.evals import run_evals, summarise

    settings = load_settings()
    results = run_evals(
        load_thesis(),
        mode="live" if live else "offline",
        client=_client(settings, live),
        model=settings.model,
    )
    typer.echo(
        "SYNTHETIC eval set (fictional decks) - this shows the harness works, nothing more.\n"
    )
    for r in results:
        missed = sorted(r.expected - r.found)
        typer.echo(
            f"{r.case:11} recall {r.recall:.0%}  labelled {r.decision:9} suggested {r.suggested or 'n/a':9} {r.seconds}s"
            + (f"  missed {missed}" if missed else "")
        )
    summary = summarise(results)
    typer.echo("\n" + json.dumps(summary, indent=2))
    if summary["decision_agreement"] is None:
        typer.echo("Decision agreement needs agent ratings: run with --live.")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the web UI."""
    import uvicorn

    from deckbrief.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
