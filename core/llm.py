"""LLM client — OpenAI-compatible API."""

import json
import httpx
from config import CONFIG
from logger import agent_logger


async def call_llm(
    messages: list,
    tools: list | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Call LLM via OpenAI-compatible API. Returns raw response dict."""
    model = model or CONFIG.model
    temperature = temperature if temperature is not None else CONFIG.temperature
    max_tokens = max_tokens or CONFIG.max_tokens

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {CONFIG.llm_api_key}",
        "Content-Type": "application/json",
    }

    agent_logger.debug(f"LLM call: model={model}, msgs={len(messages)}, tools={len(tools or [])}")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{CONFIG.llm_base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    usage = data.get("usage", {})
    agent_logger.debug(
        f"LLM response: tokens in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}"
    )
    return data


def extract_response(data: dict) -> tuple[str, list]:
    """Extract (text, tool_calls) from LLM response."""
    choice = data["choices"][0]
    msg = choice["message"]
    text = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []
    return text, tool_calls


def estimate_tokens(messages: list) -> int:
    """Rough token estimate: ~4 chars per token."""
    total = sum(
        len(str(m.get("content", ""))) + len(str(m.get("tool_calls", "")))
        for m in messages
    )
    return total // 4
