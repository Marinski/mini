"""A tiny OpenAI-compatible mock server for tests. Standard library only.

Usage::

    with MockServer() as server:
        client = Client(server.url, "test-model")
        result = client.stream_chat([{"role": "user", "content": "hi"}])
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class MockState:
    deltas: list[dict[str, Any]] = field(
        default_factory=lambda: [{"content": "Hello"}, {"content": " world"}]
    )
    usage: dict[str, Any] | None = field(
        default_factory=lambda: {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 0},
        }
    )
    delay: float = 0.02  # seconds between chunks
    status: int = 200
    body: str | None = None  # when status >= 400
    models: list[dict[str, Any]] = field(
        default_factory=lambda: [{"id": "test-model", "max_model_len": 65536}]
    )
    context_length: int | None = 65536
    tokenize_scale: int | None = 4  # None -> /tokenize returns 404
    props: dict[str, Any] | None = None
    include_usage: bool = True
    # Optional callable(payload) -> list[delta]; overrides `deltas` per request.
    responder: Any = None
    requests: list[dict[str, Any]] = field(default_factory=list)
    tokenize_calls: list[str] = field(default_factory=list)


class _Handler(BaseHTTPRequestHandler):
    state: MockState

    def log_message(self, *args: Any) -> None:  # silence
        pass

    def _json(self, code: int, payload: Any) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.endswith("/models"):
            self._json(200, {"object": "list", "data": self.state.models})
        elif self.path.endswith("/props"):
            if self.state.props is None:
                self._json(404, {"error": "no props"})
            else:
                self._json(200, self.state.props)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}
        if self.path.endswith("/tokenize"):
            self._handle_tokenize(payload)
        elif self.path.endswith("/chat/completions"):
            self._handle_chat(payload)
        else:
            self._json(404, {"error": "not found"})

    def _handle_tokenize(self, payload: dict[str, Any]) -> None:
        self.state.tokenize_calls.append(payload.get("content", ""))
        if self.state.tokenize_scale is None:
            self._json(404, {"error": "no tokenizer"})
            return
        count = max(1, len(payload.get("content", "").encode()) // self.state.tokenize_scale)
        self._json(200, {"tokens": list(range(count)), "count": count})

    def _handle_chat(self, payload: dict[str, Any]) -> None:
        self.state.requests.append(payload)
        if self.state.status >= 400:
            body = (self.state.body or "error").encode()
            self.send_response(self.state.status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        model = payload.get("model", "test-model")
        deltas = self.state.deltas
        if self.state.responder is not None:
            deltas = self.state.responder(payload)
        for delta in deltas:
            chunk = {
                "id": "cmpl-1",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            self._sse(chunk)
        self._sse(
            {
                "id": "cmpl-1",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        if self.state.include_usage and self.state.usage is not None:
            self._sse(
                {
                    "id": "cmpl-1",
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [],
                    "usage": self.state.usage,
                }
            )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _sse(self, chunk: dict[str, Any]) -> None:
        self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
        self.wfile.flush()
        if self.state.delay:
            time.sleep(self.state.delay)


class MockServer:
    def __init__(self, state: MockState | None = None) -> None:
        self.state = state or MockState()
        handler = type("_BoundHandler", (_Handler,), {"state": self.state})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        self.url = f"http://{host}:{port}/v1"

    def __enter__(self) -> MockServer:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
