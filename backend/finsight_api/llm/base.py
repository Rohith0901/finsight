"""Provider interface. Switching provider is configuration, not a code change."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The model could not be reached or answered with something unusable."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str | None = None


@dataclass
class Message:
    """Provider-neutral chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_name: str | None = None  # for role == "tool"
    tool_call_id: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]


class Provider(Protocol):
    name: str
    is_cloud: bool

    def generate(self, messages: list[Message], tools: list[ToolSpec]) -> Reply: ...
