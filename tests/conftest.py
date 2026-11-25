from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import pytest

from deckbrief.thesis import Thesis, load_thesis


@pytest.fixture
def thesis() -> Thesis:
    return load_thesis()


@dataclass
class Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, **_: Any) -> dict[str, Any]:
        if self.type == "text":
            return {"type": "text", "text": self.text}
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class Resp:
    content: list[Block]
    stop_reason: str = "tool_use"
    usage: Any = None


class FakeMessages:
    """Replays a scripted list of responses and records each request."""

    def __init__(self, responses: list[Resp]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Resp:
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[Resp]):
        self.messages = FakeMessages(responses)
