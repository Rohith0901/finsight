"""The assistant: match a known question or run a tool loop, then verify.

1. A known question (intent) is answered from tools with a template. A model may
   rephrase it; if the rephrasing changes any number, the template is used.
2. Any other question goes to the model with tools. The final answer must only
   contain numbers found in the tool results, or it is replaced by a summary.
3. If the model is unreachable, the templated or summary answer is returned.
"""

from __future__ import annotations

import json
import logging

from ..schemas import ChatRequest, ChatResponse, Fact
from .base import Message, Provider, ProviderError, ToolCall, ToolSpec
from .context import TOOLS_BY_NAME, FinanceContext, tools_for
from .intents import EXAMPLES, IntentAnswer, inr, match
from .verifier import collect, verify

log = logging.getLogger("finsight.assistant")
MAX_TOOL_ROUNDS = 4

SYSTEM_TOOLS = (
    "You are the assistant inside FinSight, a personal spending app used in India. "
    "Use the tools to get every number; never calculate, estimate or invent amounts yourself. "
    "Amounts are Indian rupees; write them like ₹1,23,456. Answer in at most three short "
    "sentences. Do not give investment advice. If the tools cannot answer the question, "
    "say so briefly."
)
SYSTEM_REPHRASE = (
    "You rewrite a personal finance app's answer so it reads naturally and kindly. Keep every "
    "number exactly as written. Do not add numbers, advice or facts that are not in the answer. "
    "Reply with the rewritten answer only, in at most three sentences."
)


class Assistant:
    def __init__(self, providers: dict[str, Provider], default: str):
        self.providers = providers
        self.default = default

    def _provider(self, requested: str) -> Provider | None:
        name = self.default if requested == "auto" else requested
        return self.providers.get(name)

    def answer(self, req: ChatRequest) -> ChatResponse:
        ctx = FinanceContext(req.transactions, req.as_of, req.balance_paise,
                             req.savings_target_paise)
        provider = self._provider(req.provider)
        question_numbers = collect(req.question)

        found = match(req.question)
        if found:
            intent_name, handler = found
            templ = handler(ctx, req.question)
            return self._rephrase(templ, provider, req.question, question_numbers)
        if provider is None:
            return self._summary(ctx, "none", fallback=False)
        return self._tool_loop(ctx, provider, req.question, question_numbers)

    # ------------------------------------------------------------ known questions

    def _rephrase(self, templ: IntentAnswer, provider: Provider | None, question: str,
                  question_numbers: set[float]) -> ChatResponse:
        plain = ChatResponse(answer=templ.text, intent=templ.intent, facts=templ.facts,
                             provider_used="none", verified=True, fallback_used=False)
        # Cloud models never see merchant names or single transactions.
        if provider is None or (provider.is_cloud and templ.sensitive):
            return plain
        try:
            reply = provider.generate(
                [Message("system", SYSTEM_REPHRASE),
                 Message("user", f"Question: {question}\nAnswer to rewrite: {templ.text}")],
                [],
            )
        except ProviderError as exc:
            log.info("rephrase skipped: %s", exc)
            return plain.model_copy(update={"fallback_used": True})
        allowed = collect(templ.data) | collect(templ.text) | question_numbers
        verdict = verify(reply.text, allowed)
        if not reply.text or not verdict.ok:
            log.info("rephrase rejected, unsupported numbers: %s", verdict.unsupported)
            return plain.model_copy(update={"fallback_used": True})
        return plain.model_copy(update={"answer": reply.text, "provider_used": provider.name})

    # ------------------------------------------------------------ open questions

    def _tool_loop(self, ctx: FinanceContext, provider: Provider, question: str,
                   question_numbers: set[float]) -> ChatResponse:
        tools = tools_for(cloud=provider.is_cloud)
        specs = [ToolSpec(t.name, t.description, t.parameters) for t in tools]
        allowed_names = {t.name for t in tools}
        messages = [Message("system", SYSTEM_TOOLS), Message("user", question)]
        results: list[dict] = []
        used: list[str] = []
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                reply = provider.generate(messages, specs)
                if not reply.tool_calls:
                    break
                messages.append(Message("assistant", reply.text, tool_calls=reply.tool_calls))
                for call in reply.tool_calls:
                    output = self._run_tool(ctx, call, allowed_names)
                    results.append(output)
                    used.append(call.name)
                    messages.append(Message("tool", json.dumps(output, ensure_ascii=False),
                                            tool_name=call.name, tool_call_id=call.id))
            else:
                reply = provider.generate(messages, [])  # rounds exhausted: ask for the answer
        except ProviderError as exc:
            log.info("assistant model unavailable: %s", exc)
            return self._summary(ctx, provider.name, fallback=True)

        allowed = collect(results) | question_numbers
        verdict = verify(reply.text, allowed)
        if not reply.text or not verdict.ok:
            log.info("answer rejected, unsupported numbers: %s", verdict.unsupported)
            return self._summary(ctx, provider.name, fallback=True)
        facts = [Fact(label="Based on", value=name.replace("_", " "))
                 for name in dict.fromkeys(used)]
        return ChatResponse(answer=reply.text, intent=None, facts=facts,
                            provider_used=provider.name, verified=True, fallback_used=False)

    @staticmethod
    def _run_tool(ctx: FinanceContext, call: ToolCall, allowed: set[str]) -> dict:
        tool = TOOLS_BY_NAME.get(call.name)
        if tool is None or call.name not in allowed:
            return {"error": f"unknown tool {call.name}"}
        try:
            return tool.run(ctx, call.arguments or {})
        except Exception:  # a tool bug must not become a 500 for the user
            log.exception("tool %s failed", call.name)
            return {"error": f"{call.name} failed"}

    # ------------------------------------------------------------ fallback

    def _summary(self, ctx: FinanceContext, provider_name: str, fallback: bool) -> ChatResponse:
        s = TOOLS_BY_NAME["month_summary"].run(ctx, {})
        lead = ("I couldn't check an answer to that question, so here's your month instead. "
                if fallback else "I can answer questions about your spending. ")
        text = (f"{lead}You've spent {inr(s['spent_so_far_rupees'])} so far this month and are "
                f"on track for about {inr(s['projected_month_end_rupees'])}. "
                f"Try asking: \"{EXAMPLES[0]}\" or \"{EXAMPLES[2]}\"")
        facts = [
            Fact(label="Spent so far", value=inr(s["spent_so_far_rupees"])),
            Fact(label="Projected month end", value=inr(s["projected_month_end_rupees"])),
        ]
        return ChatResponse(answer=text, intent=None, facts=facts, provider_used=provider_name,
                            verified=True, fallback_used=fallback)
