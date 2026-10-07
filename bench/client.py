"""Streaming OpenAI-compatible client with Protorikis's timing and parameters.

Mirrors `rikis/runtimes/base.py` (Apache-2.0) on the wire:

* one POST to ``/v1/chat/completions`` with ``stream: true``;
* thinking off    -> ``chat_template_kwargs.enable_thinking = false`` and
  ``reasoning_effort = "none"``; thinking on sends neither;
* preserve_thinking -> ``chat_template_kwargs.preserve_thinking = true``;
* **TTFT** = request sent -> first chunk carrying content or reasoning;
* **generation** = last such chunk - first such chunk;
* the chunk count is recorded next to the server's token count, because
  Protorikis counts chunks and we use ``usage.completion_tokens``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TEMPERATURE = 0.0
_CHARS_PER_TOKEN = 4  # only for the estimate when /tokenize is unavailable


@dataclass
class StreamResult:
    response: str = ""
    reasoning: str = ""
    ttft_seconds: float | None = None
    generation_seconds: float | None = None
    stream_seconds: float | None = None
    output_tokens: int | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    chunk_count: int = 0
    finish_reason: str | None = None
    status: str = "ok"
    error: str | None = None


@dataclass
class ContextWindow:
    tokens: int | None
    source: str


class Client:
    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout: float | None = 600.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = normalize_endpoint(endpoint)
        self.model = model
        self.api_key = api_key
        self._timeout = timeout
        self._transport = transport

    # -- plumbing ---------------------------------------------------------

    def _url(self, path: str) -> str:
        return self.endpoint + path

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _timeout_obj(self, timeout: float | None) -> httpx.Timeout:
        if timeout is None:
            return httpx.Timeout(None)
        return httpx.Timeout(timeout, connect=10.0)

    def _client(self, timeout: float | None, stream: bool = False) -> httpx.Client:
        return httpx.Client(
            timeout=self._timeout_obj(timeout),
            transport=self._transport,
            follow_redirects=True,
        )

    # -- chat -------------------------------------------------------------

    def build_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = DEFAULT_TEMPERATURE,
        max_tokens: int | None = None,
        thinking: bool = True,
        preserve_thinking: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chat_template_kwargs: dict[str, Any] = {}
        if not thinking:
            chat_template_kwargs["enable_thinking"] = False
            payload["reasoning_effort"] = "none"
        if preserve_thinking:
            chat_template_kwargs["preserve_thinking"] = True
        if chat_template_kwargs:
            payload["chat_template_kwargs"] = chat_template_kwargs
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = DEFAULT_TEMPERATURE,
        max_tokens: int | None = None,
        thinking: bool = True,
        preserve_thinking: bool = False,
        timeout: float | None = None,
    ) -> StreamResult:
        payload = self.build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking,
            preserve_thinking=preserve_thinking,
        )
        result = StreamResult()
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        t_start = time.perf_counter()
        t_first: float | None = None
        t_last: float | None = None
        try:
            with self._client(timeout, stream=True).stream(
                "POST",
                self._url("/chat/completions"),
                headers=self._headers(),
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", "replace")
                    result.status = "error"
                    result.error = f"HTTP {resp.status_code}: {body[:500]}"
                    return result
                for line in resp.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage")
                    if usage:
                        _absorb_usage(result, usage)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    content = delta.get("content") or ""
                    if reasoning or content:
                        now = time.perf_counter()
                        if t_first is None:
                            t_first = now
                        t_last = now
                        result.chunk_count += 1
                        if reasoning:
                            reasoning_parts.append(reasoning)
                        if content:
                            content_parts.append(content)
                    if choice.get("finish_reason"):
                        result.finish_reason = choice["finish_reason"]
        except httpx.HTTPError as exc:  # connection refused, read timeout, ...
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            return result

        t_end = time.perf_counter()
        result.response = "".join(content_parts)
        result.reasoning = "".join(reasoning_parts)
        result.ttft_seconds = (t_first - t_start) if t_first is not None else None
        result.generation_seconds = (t_last - t_first) if t_first is not None else None
        result.stream_seconds = t_end - t_start
        return result

    # -- server metadata --------------------------------------------------

    def models(self) -> list[dict[str, Any]]:
        with self._client(timeout=15.0) as client:
            resp = client.get(self._url("/models"), headers=self._headers())
            resp.raise_for_status()
            return resp.json().get("data", [])

    def context_window(self, override: int | None = None) -> ContextWindow:
        """Read the context window from the server, or use ``override``.

        Order: ``--ctx`` override, then the model metadata from ``/v1/models``
        (vLLM's ``max_model_len``, llama.cpp's ``n_ctx``/``context_length``),
        then llama.cpp's ``/props``. Returns ``tokens=None`` when unknown.
        """
        if override is not None:
            return ContextWindow(override, "cli")
        try:
            for model in self.models():
                for key in ("max_model_len", "context_length", "context_window", "n_ctx"):
                    value = model.get(key)
                    if isinstance(value, int) and value > 0:
                        return ContextWindow(value, f"models.{key}")
                meta = model.get("meta") or {}
                if isinstance(meta, dict):
                    value = meta.get("n_ctx_train") or meta.get("n_ctx")
                    if isinstance(value, int) and value > 0:
                        return ContextWindow(value, "models.meta.n_ctx")
        except (httpx.HTTPError, ValueError):
            pass
        try:
            with self._client(timeout=10.0) as client:
                resp = client.get(self._url("/../props"), headers=self._headers())
                if resp.status_code < 400:
                    data = resp.json()
                    default = data.get("default_generation_settings") or {}
                    for candidate in (data.get("n_ctx"), default.get("n_ctx")):
                        if isinstance(candidate, int) and candidate > 0:
                            return ContextWindow(candidate, "props.n_ctx")
        except (httpx.HTTPError, ValueError):
            pass
        return ContextWindow(None, "unknown")

    def count_tokens(self, text: str) -> tuple[int, bool]:
        """Return ``(tokens, estimated)`` using the server's tokenizer if it has one."""
        try:
            with self._client(timeout=20.0) as client:
                resp = client.post(
                    self._url("/tokenize"),
                    headers=self._headers(),
                    json={"content": text, "model": self.model},
                )
                if resp.status_code < 400:
                    data = resp.json()
                    tokens = data.get("tokens")
                    if isinstance(tokens, list):
                        return len(tokens), False
                    count = data.get("count") or data.get("token_count")
                    if isinstance(count, int):
                        return count, False
        except (httpx.HTTPError, ValueError):
            pass
        return estimate_tokens(text), True


def _absorb_usage(result: StreamResult, usage: dict[str, Any]) -> None:
    if isinstance(usage.get("completion_tokens"), int):
        result.output_tokens = usage["completion_tokens"]
    if isinstance(usage.get("prompt_tokens"), int):
        result.prompt_tokens = usage["prompt_tokens"]
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict) and isinstance(details.get("cached_tokens"), int):
        result.cached_tokens = details["cached_tokens"]


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // _CHARS_PER_TOKEN)


def normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"
    return endpoint
