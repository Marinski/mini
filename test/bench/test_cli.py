from bench.bench import main
from test.bench.mock_server import MockServer, MockState


def hello_responder(payload):
    content = payload["messages"][-1]["content"]
    if content.startswith("State"):
        return [{"content": "Qwen3.8-27B"}]
    return [{"content": "yes"}]


def test_cli_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "hello_world" in out
    assert "preserve_thinking_1" in out


def test_cli_run_and_report(tmp_path, capsys):
    results = str(tmp_path)
    with MockServer(MockState(responder=hello_responder)) as server:
        code = main(
            [
                "run",
                "hello_world",
                "--endpoint",
                server.url,
                "--model",
                "test-model",
                "--results",
                results,
                "--no-lock",
                "--quiet",
            ]
        )
    assert code == 0
    files = list(tmp_path.glob("hello_world__*.json"))
    assert len(files) == 1

    assert main(["report", "--results", results]) == 0
    out = capsys.readouterr().out
    assert "### test-model" in out
    assert "hello_world" in out
    assert "100%" in out


def test_cli_compare(tmp_path, capsys):
    results = str(tmp_path)
    with MockServer(MockState(responder=hello_responder)) as server:
        main(["run", "hello_world", "--endpoint", server.url, "--model", "m",
              "--results", results, "--no-lock", "--quiet"])
    run_ids = [p.stem for p in tmp_path.glob("hello_world__*.json")]
    assert len(run_ids) == 1
    assert main(["compare", run_ids[0], run_ids[0], "--results", results]) == 0
    out = capsys.readouterr().out
    assert "Agreement:" in out


def test_cli_unknown_suite(tmp_path):
    with MockServer(MockState()) as server:
        code = main(
            ["run", "nope", "--endpoint", server.url, "--model", "m",
             "--results", str(tmp_path), "--no-lock", "--quiet"]
        )
    assert code == 2
