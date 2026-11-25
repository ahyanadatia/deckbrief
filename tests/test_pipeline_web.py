from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deckbrief.config import Settings
from deckbrief.evals import run_evals, summarise
from deckbrief.pipeline import screen_sample
from deckbrief.web.app import create_app
from deckbrief.web_sources import FetchError, assert_public, html_to_text


def test_scripted_sample_end_to_end(thesis) -> None:  # type: ignore[no-untyped-def]
    b = screen_sample("gridline", thesis, mode="scripted")
    assert b.score and b.score.total == 60.0 and b.score.recommendation == "review"
    rule = [i for i in b.inconsistencies if i.origin == "rule"]
    assert len(rule) == 4
    # the agent's ARR flag duplicates a rule flag, so only the impact one is kept
    assert [i.title for i in b.inconsistencies if i.origin == "agent"] == [
        "Impact figure basis unclear"
    ]
    gap_ids = {g.criterion_id for g in b.gaps}
    assert {"competitive_position", "impact:contribution", "impact:risk"} <= gap_ids
    assert b.climate is not None and not b.climate.evidenced


def test_offline_sample_has_no_score(thesis) -> None:  # type: ignore[no-untyped-def]
    b = screen_sample("gridline", thesis, mode="offline")
    assert b.score and b.score.total is None and b.metrics == []
    assert len(b.inconsistencies) == 4


def test_eval_skeleton_runs_offline(thesis) -> None:  # type: ignore[no-untyped-def]
    s = summarise(run_evals(thesis))
    assert s["cases"] == 3 and s["flag_recall"] == 1.0 and s["decision_agreement"] is None


def test_html_text_and_ssrf_guard() -> None:
    title, text, links = html_to_text(
        "<title>T</title><script>x()</script><p>Hello <a href='/about'>about</a></p>"
    )
    assert title == "T" and "x()" not in text and links == ["/about"]
    for url in ["http://127.0.0.1/", "http://localhost/admin", "file:///etc/passwd"]:
        with pytest.raises(FetchError):
            assert_public(url)


def test_web_flow(tmp_path: Path) -> None:
    app = create_app(Settings(api_key=None, model="m", data_dir=tmp_path))
    c = TestClient(app)
    home = c.get("/")
    assert "No-key mode" in home.text
    r = c.post("/sample", data={"mode": "scripted"}, follow_redirects=False)
    job = r.headers["location"].rsplit("/", 1)[-1]
    for _ in range(50):
        st = c.get(f"/api/jobs/{job}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done", st
    page = c.get(f"/briefs/{st['brief_id']}")
    assert "Scripted sample brief" in page.text and 'href="#src-deck-p-3"' in page.text
    c.post(
        f"/briefs/{st['brief_id']}/decision",
        data={"decision": "more_info", "notes": "ask for revenue"},
    )
    assert "ask for revenue" in c.get("/history").text
    assert "more_info" in c.get("/history.csv").text
    assert c.post("/sample", data={"mode": "live"}).status_code == 400  # no key


def test_upload_flow(tmp_path: Path) -> None:
    from deckbrief.pipeline import sample_paths

    c = TestClient(create_app(Settings(api_key=None, model="m", data_dir=tmp_path)))
    with sample_paths("verdant")[0].open("rb") as fh:
        r = c.post(
            "/screen",
            files={"deck": ("d.pdf", fh, "application/pdf")},
            data={"mode": "offline"},
            follow_redirects=False,
        )
    job = r.headers["location"].rsplit("/", 1)[-1]
    for _ in range(50):
        st = c.get(f"/api/jobs/{job}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done"
    assert "Customer count differs" in c.get(f"/briefs/{st['brief_id']}").text
