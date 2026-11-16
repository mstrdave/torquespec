"""LLM diagnosis: builds the prompt and streams Claude's answer."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import anthropic

from .knowledge import KnowledgeBase

MODEL = os.environ.get("TORQUESPEC_MODEL", "claude-opus-5-5")

INSTRUCTIONS = """You are Torque Spec, a diagnostic assistant for one car: a 1990 Mazda MX-5 Miata (NA6, 1.6 L B6ZE). \
You help an owner who does their own work figure out what is wrong and fix it.

How to work:
- Start from the symptoms. Ask one or two focused questions when the answer would change the diagnosis \
(when it happens, hot or cold, sounds, smells, flash codes, recent work). Do not ask for things already given.
- Give a ranked list of likely causes for this specific car, most likely first, with the reason each fits.
- For each cause, give a cheap test that confirms or rules it out before buying parts.
- When the owner is ready to fix it, give clear steps, the tools needed, and the torque values.
- Use the reference data below for specs, codes and known issues. Values marked [verify] are less certain: \
say so and tell the owner to confirm them in the factory workshop manual. If a spec is not in the reference \
data, say you do not have it rather than guessing.
- Safety comes first. Brakes, steering, fuel leaks, overheating and anything that needs the car lifted: \
say plainly when the car should not be driven, and remind the owner to use jack stands, never just a jack.
- This car is pre-OBD-II. There is no OBD-II port; codes come from flashing the check engine light.
- Be concise. Use short paragraphs and lists. No filler."""


@dataclass
class ChatTurn:
    role: str  # "user" or "assistant"
    content: str


def build_system(kb: KnowledgeBase) -> list[dict]:
    # Stable text only, so the prompt cache hits on every turn.
    return [{
        "type": "text",
        "text": f"{INSTRUCTIONS}\n\n{kb.render_reference()}",
        "cache_control": {"type": "ephemeral"},
    }]


def build_messages(kb: KnowledgeBase, turns: list[ChatTurn]) -> list[dict]:
    messages = [{"role": t.role, "content": t.content} for t in turns]
    # Point the model at the known issues the latest message most resembles.
    hints = kb.match_issues(turns[-1].content)
    if hints:
        names = ", ".join(h["title"] for h in hints)
        messages[-1]["content"] += f"\n\n(Known issues on this model that match these words: {names}.)"
    return messages


class Diagnoser:
    def __init__(self, kb: KnowledgeBase, client: anthropic.AsyncAnthropic | None = None):
        self.kb = kb
        self.client = client

    @property
    def available(self) -> bool:
        return self.client is not None

    async def stream(self, turns: list[ChatTurn]) -> AsyncIterator[str]:
        if self.client is None:
            raise RuntimeError("No Anthropic credentials configured")
        async with self.client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            system=build_system(self.kb),
            messages=build_messages(self.kb, turns),
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            # If a safety classifier declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n_The model declined to answer this one. Try rephrasing the question._"
        elif final.stop_reason == "max_tokens":
            yield "\n\n_(Answer cut off. Ask me to continue.)_"


def load_dotenv(path: str = ".env") -> None:
    """Read KEY=VALUE lines from a .env file into the environment without overriding existing values."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def make_client() -> anthropic.AsyncAnthropic | None:
    """Return a client if credentials are available, else None (the app still serves reference data)."""
    load_dotenv()
    try:
        client = anthropic.AsyncAnthropic()
    except anthropic.AnthropicError:
        return None
    return client if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else None
