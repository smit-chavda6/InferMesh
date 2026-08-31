"""Small translation helpers shared by non-OpenAI adapters.

Anthropic and Gemini both need the OpenAI-style message list reshaped: system
prompts hoisted out, and content-part arrays flattened to plain text.
"""

from __future__ import annotations

from typing import Any

from app.schemas.chat import ChatMessage


def text_of(content: str | list[dict[str, Any]] | None) -> str:
    """Flatten OpenAI message content (string or content-part array) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts)


def split_system_and_turns(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    """Return (joined system prompt, non-system turns) from an OpenAI message list."""
    system_parts: list[str] = []
    turns: list[ChatMessage] = []
    for message in messages:
        if message.role in ("system", "developer"):
            text = text_of(message.content)
            if text:
                system_parts.append(text)
        else:
            turns.append(message)
    system = "\n\n".join(system_parts) if system_parts else None
    return system, turns
