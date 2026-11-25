from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    api_key: str | None
    model: str
    data_dir: Path

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def load_settings() -> Settings:
    _load_dotenv(Path(".env"))
    return Settings(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("DECKBRIEF_MODEL", "claude-sonnet-5-5"),
        data_dir=Path(os.environ.get("DECKBRIEF_DATA_DIR", "./data")),
    )


def _load_dotenv(path: Path) -> None:
    """Minimal .env support so there's one less dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
