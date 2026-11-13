"""LLM wrapper (Claude or Gemini): structured output as a Pydantic model, with cost tracking."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import TypeVar

from pydantic import BaseModel

from talent_agent.config import get_settings
from talent_agent.observability import observe

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# USD per million tokens (input, output). Update when pricing changes.
PRICING = {
    "claude-opus-5-5": (5.0, 25.0),
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-haiku-5-5": (1.0, 5.0),
}


class CostMeter:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.usd = 0.0
        self.priced = True  # False once a model without a known price was used
        self._lock = threading.Lock()

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        s = get_settings()
        price = PRICING.get(model) or ((s.llm_price_in, s.llm_price_out) if s.llm_price_in or s.llm_price_out else None)
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            if price:
                self.usd += input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1]
            else:
                self.priced = False


meter = CostMeter()


class Throttle:
    """Spaces calls evenly to stay under a requests-per-minute quota (shared across threads)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self, rpm: int) -> None:
        if rpm <= 0:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + 60 / rpm
        time.sleep(max(0.0, slot - now))


throttle = Throttle()
RETRYABLE = ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "timed out", "timeout")


def provider() -> str:
    s = get_settings()
    if s.llm_provider != "auto":
        return s.llm_provider
    if s.anthropic_api_key:
        return "anthropic"
    return "gemini" if s.gemini_api_key else "none"


class LLM:
    def __init__(self, model: str | None = None, fast: bool = False) -> None:
        s = get_settings()
        self.provider = provider()
        self._client = None
        if self.provider == "anthropic" and s.anthropic_api_key:
            import anthropic

            self.model = model or (s.claude_fast_model if fast else s.claude_model)
            self._client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        elif self.provider == "gemini" and s.gemini_api_key:
            from google import genai
            from google.genai import types

            self.model = model or (s.gemini_fast_model if fast else s.gemini_model)
            self._client = genai.Client(api_key=s.gemini_api_key, http_options=types.HttpOptions(timeout=s.request_timeout * 3000))
        else:
            self.model = model or ""
        self.enabled = self._client is not None

    @observe(name="llm.structured")
    def structured(self, system: str, prompt: str, schema: type[T], max_tokens: int = 4096) -> T:
        if not self.enabled:
            raise RuntimeError("No LLM key set (ANTHROPIC_API_KEY or GEMINI_API_KEY)")
        if self.provider == "gemini":
            return schema.model_validate_json(self._gemini(system, prompt, max_tokens, schema))
        return self._claude_tool(system, prompt, schema, max_tokens)

    @observe(name="llm.text")
    def text(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        if not self.enabled:
            raise RuntimeError("No LLM key set (ANTHROPIC_API_KEY or GEMINI_API_KEY)")
        if self.provider == "gemini":
            return self._gemini(system, prompt, max_tokens).strip()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        meter.add(self.model, resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def _claude_tool(self, system: str, prompt: str, schema: type[T], max_tokens: int) -> T:
        """Force Claude to call a single tool whose input schema is the Pydantic model."""
        tool = {
            "name": "submit",
            "description": f"Submit the {schema.__name__} result.",
            "input_schema": schema.model_json_schema(),
        }
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit"},
            messages=[{"role": "user", "content": prompt}],
        )
        meter.add(self.model, resp.usage.input_tokens, resp.usage.output_tokens)
        for block in resp.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise ValueError(f"No tool_use block in response: {json.dumps([b.type for b in resp.content])}")

    def _gemini(self, system: str, prompt: str, max_tokens: int, schema: type[BaseModel] | None = None) -> str:
        """Gemini JSON mode with the Pydantic schema. Retries 429/503 (free-tier quotas) with backoff."""
        from google.genai import types

        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens, temperature=0.2)
        if schema:
            cfg.response_mime_type = "application/json"
            cfg.response_json_schema = schema.model_json_schema()
        for attempt in range(4):
            throttle.wait(get_settings().gemini_rpm)
            try:
                resp = self._client.models.generate_content(model=self.model, contents=prompt, config=cfg)
                break
            except Exception as exc:
                if attempt == 3 or not any(code in str(exc) for code in RETRYABLE):
                    raise
                hint = re.search(r"retry in ([\d.]+)s", str(exc))
                time.sleep(float(hint.group(1)) + 1 if hint else 5 * 2**attempt)
        um = resp.usage_metadata
        if um:
            out = (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
            meter.add(self.model, um.prompt_token_count or 0, out)
        if not resp.text:
            raise ValueError("Empty Gemini response")
        return resp.text
