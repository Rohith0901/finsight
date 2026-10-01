"""Provider adapters against mocked HTTP, in the documented request/response shapes."""

import json

import httpx
import pytest

from finsight_api.llm.base import Message, ProviderError, ToolCall, ToolSpec
from finsight_api.llm.gemini import GeminiProvider
from finsight_api.llm.ollama import OllamaProvider

TOOLS = [ToolSpec("month_summary", "Month so far", {"type": "object", "properties": {}})]


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_tool_call_and_answer():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/api/chat" and body["stream"] is False
        if len(seen) == 1:
            assert body["tools"][0]["function"]["name"] == "month_summary"
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "",
                                  "tool_calls": [{"function": {"name": "month_summary",
                                                               "arguments": {}}}]}})
        return httpx.Response(200, json={"message": {"role": "assistant",
                                                     "content": "<think>x</think>Done."}})

    p = OllamaProvider("http://local", "qwen2.5:3b", client=client(handler))
    r = p.generate([Message("user", "hi")], TOOLS)
    assert r.tool_calls == [ToolCall("month_summary", {})]
    r = p.generate([Message("user", "hi"),
                    Message("assistant", "", tool_calls=r.tool_calls),
                    Message("tool", "{}", tool_name="month_summary")], TOOLS)
    assert r.text == "Done."
    assert seen[1]["messages"][1]["tool_calls"][0]["function"]["name"] == "month_summary"


def test_ollama_down():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError):
        OllamaProvider("http://local", "m", client=client(handler)).generate([], [])


def test_gemini_shapes():
    def handler(request):
        assert request.headers["x-goog-api-key"] == "k"
        assert request.url.path.endswith("/models/gemini-x:generateContent")
        body = json.loads(request.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "sys"
        assert body["tools"][0]["functionDeclarations"][0]["name"] == "month_summary"
        roles = [c["role"] for c in body["contents"]]
        assert roles == ["user", "model", "user"]
        assert "functionResponse" in body["contents"][2]["parts"][0]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "Hello"}, {"functionCall": {"name": "month_summary", "args": {}}}]}}]})

    p = GeminiProvider("k", "gemini-x", client=client(handler))
    r = p.generate([Message("system", "sys"), Message("user", "hi"),
                    Message("assistant", "", tool_calls=[ToolCall("month_summary", {})]),
                    Message("tool", "{}", tool_name="month_summary")], TOOLS)
    assert r.text == "Hello" and r.tool_calls[0].name == "month_summary"
