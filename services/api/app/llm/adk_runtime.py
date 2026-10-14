"""One bounded ADK language-agent turn, using the existing guarded SDK transport.

The LLMClient owns quotas, timeouts, retries and caches. This adapter lets ADK own
agent invocation/session/output without creating a second unguarded network path.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field

_STEP = ContextVar("relief_ai_step", default="LanguageAgent")


@contextmanager
def ai_step(name: str) -> Iterator[None]:
    token = _STEP.set(name)
    try:
        yield
    finally:
        _STEP.reset(token)


def current_step() -> str:
    return _STEP.get()


class GuardedTransport(BaseLlm):
    """Transport is supplied by LLMClient after it acquires its quota/slot."""
    call: Callable[[], str] = Field(exclude=True)

    async def generate_content_async(self, llm_request, stream=False):
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=self.call())]))


def run_text_agent(name: str, model: str, instruction: str, prompt: str, call: Callable[[], str]) -> str:
    async def run() -> str:
        agent = LlmAgent(
            name=name,
            model=GuardedTransport(model=model, call=call),
            instruction=lambda ctx: instruction,
            output_key="validated_reply",
        )
        runner = InMemoryRunner(agent=agent, app_name="relief_language")
        try:
            session = await runner.session_service.create_session(app_name="relief_language", user_id="synthetic")
            reply = ""
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            ):
                if event.is_final_response() and event.content:
                    reply = "".join(part.text or "" for part in event.content.parts or [])
            return reply
        finally:
            await runner.close()
    return asyncio.run(run())
