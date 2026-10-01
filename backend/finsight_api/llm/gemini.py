"""Gemini through the generateContent REST endpoint (opt-in, cloud).

Only aggregate facts may reach this provider: the assistant offers it the
aggregate tools alone and never passes merchant-level detail to it.
Google's terms allow free-tier prompts to be used for product improvement and
read by reviewers, so use a paid key if you enable this.
"""

from __future__ import annotations

import httpx

from .base import Message, ProviderError, Reply, ToolCall, ToolSpec

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"
    is_cloud = True

    def __init__(self, api_key: str, model: str, timeout_s: float = 30.0,
                 client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=timeout_s)

    @staticmethod
    def _contents(messages: list[Message]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents: list[dict] = []
        for m in messages:
            if m.role == "user":
                contents.append({"role": "user", "parts": [{"text": m.content}]})
            elif m.role == "assistant":
                parts: list[dict] = []
                if m.content:
                    parts.append({"text": m.content})
                parts += [
                    {"functionCall": {"name": c.name, "args": c.arguments}} for c in m.tool_calls
                ]
                contents.append({"role": "model", "parts": parts})
            elif m.role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": m.tool_name or "tool",
                                    "response": {"content": m.content},
                                }
                            }
                        ],
                    }
                )
        return system, contents

    def generate(self, messages: list[Message], tools: list[ToolSpec]) -> Reply:
        system, contents = self._contents(messages)
        body: dict = {"contents": contents, "generationConfig": {"temperature": 0.2}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }
            ]
        try:
            resp = self.client.post(
                API.format(model=self.model),
                json=body,
                headers={"x-goog-api-key": self.api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"gemini unavailable: {type(exc).__name__}") from exc

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts, calls = [], []
        for part in parts:
            if "text" in part:
                texts.append(part["text"])
            fc = part.get("functionCall")
            if fc and fc.get("name"):
                calls.append(ToolCall(name=fc["name"], arguments=fc.get("args") or {}))
        return Reply(text="".join(texts).strip(), tool_calls=calls)
