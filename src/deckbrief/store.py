"""SQLite storage for briefs and the investor decisions made on them."""

from __future__ import annotations

import csv
import io
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deckbrief.models import Brief, Decision

SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    id TEXT PRIMARY KEY, company TEXT, created_at TEXT, mode TEXT,
    recommendation TEXT, score REAL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id TEXT NOT NULL REFERENCES briefs(id),
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'pass', 'more_info')),
    notes TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def save(self, brief: Brief) -> None:
        s = brief.score
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO briefs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    brief.id,
                    brief.company,
                    brief.created_at.isoformat(),
                    brief.mode,
                    s.recommendation if s else None,
                    s.total if s else None,
                    brief.model_dump_json(),
                ),
            )
            self.db.commit()

    def get(self, brief_id: str) -> Brief | None:
        row = self.db.execute("SELECT body FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        return Brief.model_validate_json(row["body"]) if row else None

    def decide(self, brief_id: str, decision: Decision, notes: str = "") -> None:
        if self.get(brief_id) is None:
            raise KeyError(brief_id)
        with self._lock:
            self.db.execute(
                "INSERT INTO decisions (brief_id, decision, notes, decided_at) VALUES (?, ?, ?, ?)",
                (
                    brief_id,
                    decision,
                    notes.strip(),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            self.db.commit()

    def decisions(self, brief_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT decision, notes, decided_at FROM decisions WHERE brief_id = ? ORDER BY id DESC",
            (brief_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def history(self) -> list[dict[str, Any]]:
        """Every brief with its latest decision (if any), newest first."""
        rows = self.db.execute(
            """
            SELECT b.id, b.company, b.created_at, b.mode, b.recommendation, b.score,
                   d.decision, d.notes, d.decided_at
            FROM briefs b
            LEFT JOIN decisions d ON d.id = (
                SELECT id FROM decisions WHERE brief_id = b.id ORDER BY id DESC LIMIT 1)
            ORDER BY b.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def export_csv(self) -> str:
        buf = io.StringIO()
        rows = self.history()
        fields = [
            "id",
            "company",
            "created_at",
            "mode",
            "recommendation",
            "score",
            "decision",
            "notes",
            "decided_at",
        ]
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()
