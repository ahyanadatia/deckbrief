"""FastAPI web UI: upload a deck, watch progress, read the brief, record a decision."""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deckbrief.checks import format_value
from deckbrief.config import Settings, load_settings
from deckbrief.models import Brief, Decision, Mode
from deckbrief.pipeline import sample_paths, screen, screen_sample
from deckbrief.store import Store
from deckbrief.thesis import Thesis, load_thesis

HERE = Path(__file__).resolve().parent
MAX_UPLOAD = 20_000_000


def anchor(source_id: str) -> str:
    return "src-" + re.sub(r"[^a-z0-9]+", "-", source_id.lower()).strip("-")


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    events: list[str] = field(default_factory=list)
    brief_id: str | None = None
    error: str | None = None


class Jobs:
    def __init__(self) -> None:
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def start(self, fn: Callable[[Callable[[str], None]], Brief], store: Store) -> Job:
        job = Job(id=uuid.uuid4().hex[:10])
        with self.lock:
            self.jobs[job.id] = job

        def run() -> None:
            try:
                brief = fn(job.events.append)
                store.save(brief)
                job.brief_id = brief.id
                job.status = "done"
            except Exception as exc:  # shown to the user on the progress page
                job.error = str(exc) or exc.__class__.__name__
                job.status = "error"

        self.pool.submit(run)
        return job


def anthropic_client(settings: Settings) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=settings.api_key)


def create_app(
    settings: Settings | None = None,
    thesis: Thesis | None = None,
    client_factory: Callable[[Settings], Any] = anthropic_client,
) -> FastAPI:
    settings = settings or load_settings()
    thesis = thesis or load_thesis()
    store = Store(settings.data_dir / "deckbrief.db")
    jobs = Jobs()
    app = FastAPI(title="deckbrief")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["anchor"] = anchor
    templates.env.filters["figure"] = format_value
    templates.env.globals.update(has_key=settings.has_key, model=settings.model, thesis=thesis)

    def page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx)

    def client_for(mode: str) -> Any:
        if mode != "live":
            return None
        if not settings.has_key:
            raise HTTPException(400, "Live mode needs ANTHROPIC_API_KEY in .env")
        return client_factory(settings)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return page(request, "index.html", recent=store.history()[:5])

    @app.post("/screen")
    def start_screen(
        deck: Annotated[UploadFile, File()],
        website: Annotated[str, Form()] = "",
        mode: Annotated[str, Form()] = "offline",
    ) -> RedirectResponse:
        if mode not in {"offline", "live"}:
            raise HTTPException(400, "bad mode")
        client = client_for(mode)
        uploads = settings.data_dir / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        dest = uploads / f"{uuid.uuid4().hex[:8]}.pdf"
        with dest.open("wb") as fh:
            shutil.copyfileobj(deck.file, fh, length=1 << 20)
        if dest.stat().st_size > MAX_UPLOAD:
            dest.unlink()
            raise HTTPException(413, "Deck is larger than 20 MB")
        job = jobs.start(
            lambda emit: screen(
                dest,
                thesis,
                website=website.strip() or None,
                mode=cast(Mode, mode),
                client=client,
                model=settings.model,
                emit=emit,
            ),
            store,
        )
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.post("/sample")
    def start_sample(
        slug: Annotated[str, Form()] = "gridline", mode: Annotated[str, Form()] = "scripted"
    ) -> RedirectResponse:
        if mode not in {"offline", "scripted", "live"} or slug not in {
            "gridline",
            "brightloop",
            "verdant",
        }:
            raise HTTPException(400, "bad sample request")
        client = client_for(mode)
        job = jobs.start(
            lambda emit: screen_sample(
                slug,
                thesis,
                mode=cast(Mode, mode),
                client=client,
                model=settings.model,
                emit=emit,
            ),
            store,
        )
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str) -> HTMLResponse:
        if job_id not in jobs.jobs:
            raise HTTPException(404)
        return page(request, "job.html", job_id=job_id)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.jobs.get(job_id)
        if job is None:
            raise HTTPException(404)
        return {
            "status": job.status,
            "events": job.events,
            "brief_id": job.brief_id,
            "error": job.error,
        }

    @app.get("/briefs/{brief_id}", response_class=HTMLResponse)
    def brief_page(request: Request, brief_id: str) -> HTMLResponse:
        brief = store.get(brief_id)
        if brief is None:
            raise HTTPException(404)
        return page(request, "brief.html", b=brief, decisions=store.decisions(brief_id))

    @app.get("/briefs/{brief_id}/json")
    def brief_json(brief_id: str) -> Response:
        brief = store.get(brief_id)
        if brief is None:
            raise HTTPException(404)
        return Response(brief.model_dump_json(indent=2), media_type="application/json")

    @app.post("/briefs/{brief_id}/decision")
    def decide(
        brief_id: str,
        decision: Annotated[str, Form()],
        notes: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        if decision not in {"approve", "pass", "more_info"}:
            raise HTTPException(400, "bad decision")
        try:
            store.decide(brief_id, cast(Decision, decision), notes[:2000])
        except KeyError as exc:
            raise HTTPException(404) from exc
        return RedirectResponse(f"/briefs/{brief_id}#decision", status_code=303)

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request) -> HTMLResponse:
        return page(request, "history.html", rows=store.history())

    @app.get("/history.csv")
    def history_csv() -> PlainTextResponse:
        return PlainTextResponse(
            store.export_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=deckbrief-decisions.csv"},
        )

    @app.get("/sample-deck.pdf")
    def sample_deck() -> FileResponse:
        return FileResponse(sample_paths("gridline")[0], media_type="application/pdf")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "llm": settings.has_key}

    return app
