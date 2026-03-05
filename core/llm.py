"""LLM client — OpenAI-compatible API."""

import json
from typing import AsyncGenerator
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
    """Call LLM (non-streaming). Returns raw response dict."""
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


async def call_llm_stream(
    messages: list,
    tools: list | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Call LLM with streaming. Yields chunks:
      {"type": "delta", "text": "..."}      — incremental text token
      {"type": "tool_calls", "tool_calls": [...]}  — tool calls (assembled at end)
      {"type": "done", "usage": {...}}       — stream finished

    Tool calls are buffered and emitted as a single event at the end
    (OpenAI streams them as partial JSON across many chunks).
    """
    model = model or CONFIG.model
    temperature = temperature if temperature is not None else CONFIG.temperature
    max_tokens = max_tokens or CONFIG.max_tokens

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {
        "Authorization": f"Bearer {CONFIG.llm_api_key}",
        "Content-Type": "application/json",
    }

    agent_logger.debug(f"LLM stream: model={model}, msgs={len(messages)}, tools={len(tools or [])}")

    # Accumulate tool call deltas across chunks
    tool_calls_buf: dict[int, dict] = {}  # index → partial tool call
    usage: dict = {}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{CONFIG.llm_base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Capture usage if present (stream_options)
                if chunk.get("usage"):
                    usage = chunk["usage"]

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})

                # Text token — skip empty strings and reasoning fields
                content = delta.get("content")
                if content:
                    yield {"type": "delta", "text": content}
                # reasoning_content is internal chain-of-thought — skip it

                # Tool call deltas — buffer and assemble
                tc_deltas = delta.get("tool_calls", [])
                for tc_delta in tc_deltas:
                    idx = tc_delta.get("index", 0)
                    if idx not in tool_calls_buf:
                        tool_calls_buf[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    buf = tool_calls_buf[idx]
                    if tc_delta.get("id"):
                        buf["id"] += tc_delta["id"]
                    fn = tc_delta.get("function", {})
                    if fn.get("name"):
                        buf["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        buf["function"]["arguments"] += fn["arguments"]

    # Emit assembled tool calls
    if tool_calls_buf:
        tool_calls = [tool_calls_buf[i] for i in sorted(tool_calls_buf)]
        yield {"type": "tool_calls", "tool_calls": tool_calls}

    yield {"type": "done", "usage": usage}


def extract_response(data: dict) -> tuple[str, list]:
    """Extract (text, tool_calls) from non-streaming LLM response."""
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
