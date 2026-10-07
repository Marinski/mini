import pytest

from bench.client import Client, estimate_tokens, normalize_endpoint
from test.bench.mock_server import MockServer, MockState


def test_stream_content_timing_and_usage():
    state = MockState(
        deltas=[{"content": "Hello"}, {"content": " world"}],
        delay=0.01,
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 7},
        },
    )
    with MockServer(state) as server:
        result = Client(server.url, "test-model").stream_chat(
            [{"role": "user", "content": "hi"}]
        )
    assert result.status == "ok"
    assert result.response == "Hello world"
    assert result.reasoning == ""
    assert result.chunk_count == 2
    assert result.output_tokens == 2
    assert result.prompt_tokens == 10
    assert result.cached_tokens == 7
    assert result.ttft_seconds is not None and result.ttft_seconds >= 0
    assert result.generation_seconds is not None and result.generation_seconds >= 0.005
    assert result.stream_seconds >= result.generation_seconds


def test_ttft_counts_reasoning_chunk():
    state = MockState(
        deltas=[{"reasoning_content": "think"}, {"content": "answer"}],
        delay=0.01,
    )
    with MockServer(state) as server:
        result = Client(server.url, "test-model").stream_chat(
            [{"role": "user", "content": "hi"}]
        )
    assert result.reasoning == "think"
    assert result.response == "answer"
    assert result.chunk_count == 2
    assert result.ttft_seconds is not None


def test_payload_defaults_and_thinking_off():
    state = MockState()
    with MockServer(state) as server:
        client = Client(server.url, "test-model")
        client.stream_chat([{"role": "user", "content": "hi"}], thinking=False)
        _ = client.models()
    payload = state.requests[0]
    assert payload["model"] == "test-model"
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["temperature"] == 0.0
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["reasoning_effort"] == "none"
    assert "max_tokens" not in payload


def test_payload_thinking_on_preserves_nothing():
    state = MockState()
    with MockServer(state) as server:
        Client(server.url, "m").stream_chat(
            [{"role": "user", "content": "hi"}], thinking=True, max_tokens=512
        )
    payload = state.requests[0]
    assert "chat_template_kwargs" not in payload
    assert "reasoning_effort" not in payload
    assert payload["max_tokens"] == 512


def test_payload_preserve_thinking():
    state = MockState()
    with MockServer(state) as server:
        Client(server.url, "m").stream_chat(
            [{"role": "user", "content": "hi"}], thinking=True, preserve_thinking=True
        )
    assert state.requests[0]["chat_template_kwargs"] == {"preserve_thinking": True}


def test_api_key_header():
    state = MockState()
    captured = {}
    with MockServer(state) as server:
        Client(server.url, "m", api_key="secret").stream_chat(
            [{"role": "user", "content": "hi"}]
        )
    # The mock does not capture headers, so just assert the call succeeded;
    # header construction is covered directly.
    captured = Client("http://x", "m", api_key="secret")._headers()
    assert captured["Authorization"] == "Bearer secret"


def test_error_status_is_recorded_not_raised():
    state = MockState(status=400, body="exceeds context")
    with MockServer(state) as server:
        result = Client(server.url, "m").stream_chat(
            [{"role": "user", "content": "hi"}]
        )
    assert result.status == "error"
    assert "400" in result.error
    assert "exceeds context" in result.error


def test_context_window_from_models():
    state = MockState(models=[{"id": "m", "max_model_len": 4096}])
    with MockServer(state) as server:
        window = Client(server.url, "m").context_window()
    assert window.tokens == 4096
    assert window.source == "models.max_model_len"


def test_context_window_llama_server_meta_prefers_runtime_n_ctx():
    # llama-server -c 65536 on a 262K model: meta carries both; the window is n_ctx (7 Oct parity run).
    state = MockState(models=[{"id": "m", "meta": {"n_ctx": 65536, "n_ctx_train": 262144}}])
    with MockServer(state) as server:
        window = Client(server.url, "m").context_window()
    assert window.tokens == 65536
    assert window.source == "models.meta.n_ctx"


def test_context_window_override_wins():
    with MockServer(MockState()) as server:
        window = Client(server.url, "m").context_window(override=1024)
    assert window.tokens == 1024
    assert window.source == "cli"


def test_context_window_from_props():
    state = MockState(
        models=[{"id": "m"}],
        props={"default_generation_settings": {"n_ctx": 8192}},
    )
    with MockServer(state) as server:
        window = Client(server.url, "m").context_window()
    assert window.tokens == 8192
    assert window.source == "props.n_ctx"


def test_context_window_unknown():
    state = MockState(models=[{"id": "m"}], props=None)
    with MockServer(state) as server:
        window = Client(server.url, "m").context_window()
    assert window.tokens is None
    assert window.source == "unknown"


def test_count_tokens_server():
    with MockServer(MockState(tokenize_scale=4)) as server:
        tokens, estimated = Client(server.url, "m").count_tokens("a" * 40)
    assert estimated is False
    assert tokens == 10


def test_count_tokens_fallback():
    with MockServer(MockState(tokenize_scale=None)) as server:
        tokens, estimated = Client(server.url, "m").count_tokens("a" * 40)
    assert estimated is True
    assert tokens == estimate_tokens("a" * 40) == 10


def test_normalize_endpoint():
    assert normalize_endpoint("http://h:1/v1") == "http://h:1/v1"
    assert normalize_endpoint("http://h:1/v1/") == "http://h:1/v1"
    assert normalize_endpoint("http://h:1") == "http://h:1/v1"


def test_estimate_tokens_never_zero():
    assert estimate_tokens("") == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_count_tokens_uses_root_tokenize_when_v1_has_none():
    # llama-server serves /tokenize at the root only; /v1/tokenize is a 404 there.
    import httpx

    with MockServer(MockState(tokenize_scale=4)) as server:
        client = Client(server.url, "m")
        assert client.endpoint.endswith("/v1")
        tokens, estimated = client.count_tokens("a" * 40)
        root_hit = httpx.post(client.endpoint[:-3] + "/tokenize", json={"content": "a" * 40}).status_code
    assert estimated is False and tokens == 10
    assert root_hit == 200
