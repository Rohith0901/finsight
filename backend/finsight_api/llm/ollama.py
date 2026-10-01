"""Local model through Ollama's /api/chat (tool calling, non-streaming)."""

from __future__ import annotations

import json
import re

import httpx

from .base import Message, ProviderError, Reply, ToolCall, ToolSpec

_THINK = re.compile(r"<think>.*?</think>", re.S)


class OllamaProvider:
    name = "ollama"
    is_cloud = False

    def __init__(self, url: str, model: str, timeout_s: float = 30.0,
                 client: httpx.Client | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout_s)

    @staticmethod
    def _message(m: Message) -> dict:
        out: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            out["tool_calls"] = [
                {"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls
            ]
        return out

    def generate(self, messages: list[Message], tools: list[ToolSpec]) -> Reply:
        body = {
            "model": self.model,
            "messages": [self._message(m) for m in messages],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        try:
            resp = self.client.post(f"{self.url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"ollama unavailable: {type(exc).__name__}") from exc

        message = data.get("message") or {}
        calls = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):  # some models return a JSON string
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            if fn.get("name"):
                calls.append(ToolCall(name=fn["name"], arguments=args))
        text = _THINK.sub("", message.get("content") or "").strip()
        return Reply(text=text, tool_calls=calls)
