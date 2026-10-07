import threading
import time
from pathlib import Path
from typing import ClassVar

import pytest

from bench.client import Client
from bench.results import iter_index
from bench.runner import endpoint_lock, run
from bench.schemas import validate_run
from bench.suites.base import PASS, Check, Job, Prompt, Suite
from bench.suites.hello_world import HelloWorld
from test.bench.mock_server import MockServer, MockState

ROOT = str(Path(__file__).resolve().parents[2])


class FakeSuite(Suite):
    id = "fake"
    profiles = ("default",)
    default_params: ClassVar[dict] = {
        "thinking": False,
        "temperature": 0.0,
        "multi_turn": True,
        "preserve_thinking": False,
    }

    def __init__(self, texts, params=None):
        self.texts = texts
        self.params = params or {}

    def build(self, profile, ctx):
        return [
            Job(
                id="fake",
                prompts=[Prompt(f"turn{i + 1}", t) for i, t in enumerate(self.texts)],
                params=dict(self.params),
            )
        ]

    def check(self, job, subjobs):
        return [Check(PASS, "fake") for _ in subjobs]


def hello_responder(payload):
    content = payload["messages"][-1]["content"]
    if content.startswith("State"):
        return [{"content": "Qwen3.8-27B"}]
    return [{"content": "yes"}]


def test_run_hello_world_end_to_end(tmp_path):
    with MockServer(MockState(responder=hello_responder, delay=0.005)) as server:
        client = Client(server.url, "test-model")
        record = run(HelloWorld(), "default", client, results_dir=tmp_path, lock=False)

    validate_run(record)
    assert record["suite"] == "hello_world"
    assert record["summary"]["passed"] == 3
    assert record["summary"]["failed"] == 0
    assert record["summary"]["pass_rate"] == 1.0
    assert record["context_window"] == 65536
    assert (tmp_path / f"{record['run_id']}.json").exists()
    assert len(list(iter_index(tmp_path))) == 1

    # the multi-turn job replayed the conversation
    assert len(server.state.requests) == 3
    assert len(server.state.requests[1]["messages"]) == 3
    assert server.state.requests[1]["messages"][1]["role"] == "assistant"


def test_run_writes_expected_job_shape(tmp_path):
    def two_chunks(payload):
        return [{"content": "Qwen"}, {"content": "3.8-27B"}]

    with MockServer(MockState(responder=two_chunks, delay=0.01)) as server:
        record = run(HelloWorld(), "default", Client(server.url, "m"), results_dir=tmp_path, lock=False)
    sub = record["jobs"][0]["sub_jobs"][0]
    assert sub["status"] == "pass"
    assert sub["prompt_bytes"] > 0
    assert sub["output_tokens"] is not None
    assert sub["tokens_per_second"] is not None


def test_context_window_skip_is_recorded_not_an_error(tmp_path):
    suite = FakeSuite(["a" * 10, "b" * 10])
    state = MockState(tokenize_scale=1)
    with MockServer(state) as server:
        record = run(
            suite,
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 1000},
            results_dir=tmp_path,
            ctx_override=50,
            lock=False,
        )
    subs = record["jobs"][0]["sub_jobs"]
    assert [s["status"] for s in subs] == ["skipped", "skipped"]
    assert "exceeds context" in subs[0]["reason"]
    assert "previous turn exceeded context" in subs[1]["reason"]
    assert state.requests == []  # nothing was sent


def test_context_window_fits_is_sent(tmp_path):
    suite = FakeSuite(["a" * 10, "b" * 10])
    state = MockState(tokenize_scale=1, responder=lambda p: [{"content": "ok"}])
    with MockServer(state) as server:
        record = run(
            suite,
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 100},
            results_dir=tmp_path,
            ctx_override=2000,
            lock=False,
        )
    assert [s["status"] for s in record["jobs"][0]["sub_jobs"]] == ["pass", "pass"]
    assert len(state.requests) == 2


def test_error_stops_the_job(tmp_path):
    suite = FakeSuite(["a", "b"])
    state = MockState(status=400, body="boom")
    with MockServer(state) as server:
        record = run(
            suite,
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 10},
            results_dir=tmp_path,
            ctx_override=99_999,
            lock=False,
        )
    subs = record["jobs"][0]["sub_jobs"]
    assert subs[0]["status"] == "error"
    assert "400" in subs[0]["reason"]
    assert subs[1]["status"] == "skipped"
    assert "previous turn errored" in subs[1]["reason"]


def test_error_does_not_stop_independent_prompts(tmp_path):
    # memory_recall_1 jobs hold independent prompts: one oversized prompt must not skip the rest.
    suite = FakeSuite(["a", "b"], params={"multi_turn": False})
    state = MockState(status=400, body="boom")
    with MockServer(state) as server:
        record = run(
            suite,
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 10, "multi_turn": False},
            results_dir=tmp_path,
            ctx_override=99_999,
            lock=False,
        )
    subs = record["jobs"][0]["sub_jobs"]
    assert [s["status"] for s in subs] == ["error", "error"]


def test_endpoint_lock_serializes_threads(tmp_path):
    path = tmp_path / "e.lock"
    order = []

    def worker(name, delay):
        with endpoint_lock(path):
            order.append(("enter", name))
            time.sleep(delay)
            order.append(("exit", name))

    first = threading.Thread(target=worker, args=("a", 0.3))
    second = threading.Thread(target=worker, args=("b", 0.0))
    first.start()
    time.sleep(0.05)
    second.start()
    first.join()
    second.join()
    assert order == [("enter", "a"), ("exit", "a"), ("enter", "b"), ("exit", "b")]


def test_endpoint_lock_across_processes(tmp_path):
    import subprocess
    import sys

    lock = tmp_path / "p.lock"
    log = tmp_path / "log.txt"
    code = (
        "import sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "from bench.runner import endpoint_lock\n"
        "with endpoint_lock(Path(sys.argv[1])):\n"
        "    with Path(sys.argv[2]).open('a') as f: f.write(sys.argv[3] + ' start ' + str(time.time()) + '\\n')\n"
        "    time.sleep(0.4)\n"
        "    with Path(sys.argv[2]).open('a') as f: f.write(sys.argv[3] + ' end ' + str(time.time()) + '\\n')\n"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", code, str(lock), str(log), name])
        for name in ("a", "b")
    ]
    for proc in procs:
        assert proc.wait(timeout=20) == 0

    events = []
    for line in log.read_text().splitlines():
        name, kind, stamp = line.rsplit(" ", 2)
        events.append((name, kind, float(stamp)))
    assert len(events) == 4
    spans = {}
    for name, kind, stamp in events:
        spans.setdefault(name, {})[kind] = stamp
    a, b = spans["a"], spans["b"]
    # the two critical sections must not overlap
    assert b["start"] >= a["end"] - 0.01 or a["start"] >= b["end"] - 0.01


THREE = Path(__file__).resolve().parents[2] / "bench" / "data" / "three.module.js"


@pytest.mark.skipif(not THREE.exists(), reason="run bench/data/setup.py")
def test_multi_turn_2_turn4_skipped_with_context_reason(tmp_path):
    from bench import data
    from bench.runner import render_messages
    from bench.suites.multi_turn_2 import MultiTurn2

    ctx = data.Context(three_js_lines=data.three_js_lines())
    job = MultiTurn2().build("default", ctx)[0]
    # Token counts the mock tokenizer (scale 4) will report per turn, with the
    # short "ok" answers the responder gives.
    history = []
    sizes = []
    for prompt in job.prompts:
        messages = history + [{"role": "user", "content": prompt.text}]
        sizes.append(len(render_messages(messages).encode()) // 4)
        history += [
            {"role": "user", "content": prompt.text},
            {"role": "assistant", "content": "ok"},
        ]
    window = sizes[2] + 50  # turn 3 fits, turn 4 (16 max_tokens) does not

    state = MockState(
        tokenize_scale=4,
        models=[{"id": "m", "max_model_len": window}],
        responder=lambda p: [{"content": "ok"}],
    )
    with MockServer(state) as server:
        record = run(
            MultiTurn2(),
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 16},
            ctx=ctx,
            results_dir=tmp_path,
            lock=False,
        )
    subs = record["jobs"][0]["sub_jobs"]
    assert [s["status"] for s in subs[:3]] == ["pass", "pass", "pass"]
    assert subs[3]["status"] == "skipped"
    assert "exceeds context" in subs[3]["reason"]
    assert len(state.requests) == 3  # the fourth turn was never sent


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_server_context_refusal_is_skipped_not_an_error(tmp_path):
    # Strata has no /tokenize, so the bytes/4 estimate let a 73K-token turn through on a 64K
    # window and the server refused it with a 400 (7 Oct 2026): that is a skip, like the pre-check.
    suite = FakeSuite(["a", "b"])
    state = MockState(
        status=400,
        tokenize_scale=None,
        body='{"error": {"message": "prompt (73706 tokens) + max tokens (1024) exceeds the context (65536)"}}',
    )
    with MockServer(state) as server:
        record = run(
            suite,
            "default",
            Client(server.url, "m"),
            overrides={"max_tokens": 10},
            results_dir=tmp_path,
            ctx_override=99_999,
            lock=False,
        )
    subs = record["jobs"][0]["sub_jobs"]
    assert subs[0]["status"] == "skipped"
    assert subs[0]["reason"].startswith("exceeds context (server)")
    assert subs[1]["status"] == "skipped"
    assert "previous turn exceeded context" in subs[1]["reason"]
