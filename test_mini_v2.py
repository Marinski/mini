"""Behaviour tests for mini_harness_v2 (run in the agent-trial image; see README.md)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import openai
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import mini_harness_v2 as mini


@pytest.fixture
def work(tmp_path):
    return tmp_path


def edit(work, **args):
    return mini.run_tool("edit", args, work)


# --- edit -------------------------------------------------------------------------------------

def test_two_disjoint_edits_apply_in_one_call_with_a_diff_for_each(work):
    lines = [f"line {i}" for i in range(1, 41)]
    (work / "a.py").write_text("\n".join(lines) + "\n")

    out = edit(work, path="a.py", edits=[{"old": "line 5\n", "new": "FIVE\n"},
                                         {"old": "line 30\n", "new": "THIRTY\n"}])

    text = (work / "a.py").read_text()
    assert out.startswith("ok")
    assert "FIVE\n" in text and "THIRTY\n" in text and "line 5\n" not in text
    assert "@@ -2,7 +2,7 @@" in out and "@@ -27,7 +27,7 @@" in out
    assert "-line 5" in out and "+THIRTY" in out


def test_overlapping_edits_are_rejected_and_the_file_is_unchanged(work):
    (work / "a.py").write_text("alpha beta gamma\n")

    out = edit(work, path="a.py", edits=[{"old": "alpha beta", "new": "x"},
                                         {"old": "beta gamma", "new": "y"}])

    assert out.startswith("error") and "overlap" in out
    assert (work / "a.py").read_text() == "alpha beta gamma\n"


@pytest.mark.parametrize("old, count", [("missing", 0), ("dup", 2)])
def test_an_edit_that_does_not_match_once_names_the_edit_and_changes_nothing(work, old, count):
    (work / "a.py").write_text("dup\nkeep\ndup\n")

    out = edit(work, path="a.py", edits=[{"old": "keep", "new": "KEPT"}, {"old": old, "new": "z"}])

    assert out.startswith("error: edit 2") and f"found {count} times" in out
    assert (work / "a.py").read_text() == "dup\nkeep\ndup\n"


def test_the_v1_old_new_shape_still_works(work):
    (work / "a.py").write_text("x = 1\n")

    assert edit(work, path="a.py", old="x = 1", new="x = 2").startswith("ok")
    assert (work / "a.py").read_text() == "x = 2\n"


def test_the_v1_shape_without_new_is_an_error_not_a_deletion(work):
    (work / "a.py").write_text("x = 1\n")

    assert edit(work, path="a.py", old="x = 1").startswith("error: edit 1 needs")
    assert (work / "a.py").read_text() == "x = 1\n"


@pytest.mark.parametrize("edits", [json.dumps([{"old": "x = 1", "new": "x = 2"}]),
                                   {"old": "x = 1", "new": "x = 2"}])
def test_edits_sent_as_a_json_string_or_a_single_object_are_accepted(work, edits):
    (work / "a.py").write_text("x = 1\n")

    assert edit(work, path="a.py", edits=edits).startswith("ok")
    assert (work / "a.py").read_text() == "x = 2\n"


def test_the_diff_stays_readable_when_the_file_has_no_final_newline(work):
    (work / "a.py").write_text("x = 1")

    out = edit(work, path="a.py", edits=[{"old": "x = 1", "new": "x = 2"}])

    assert "-x = 1\n+x = 2\n" in out


@pytest.mark.parametrize("item, message", [({"old": "x"}, "needs 'old' and 'new'"),
                                           ("x", "needs 'old' and 'new'"),
                                           ({"old": "", "new": "y"}, "'old' is empty")])
def test_malformed_edits_get_a_clear_error_and_change_nothing(work, item, message):
    (work / "a.py").write_text("x = 1\n")

    out = edit(work, path="a.py", edits=[item])

    assert out.startswith("error: edit 1") and message in out
    assert (work / "a.py").read_text() == "x = 1\n"


def test_a_long_diff_is_cut(work):
    (work / "a.py").write_text("\n".join(f"v{i} = {i}" for i in range(500)) + "\n")

    out = edit(work, path="a.py", edits=[{"old": "v0 = 0\n", "new": "".join(
        f"w{i} = {i}\n" for i in range(500))}])

    assert out.startswith("ok") and out.endswith("[diff cut]") and len(out) < 1600


# --- read -------------------------------------------------------------------------------------

def test_read_returns_2000_lines_and_says_where_to_continue(work):
    (work / "big.txt").write_text("\n".join("x" for _ in range(5000)) + "\n")

    out = mini.run_tool("read", {"path": "big.txt"}, work)

    rows = out.splitlines()
    assert rows[0] == "1\tx" and rows[1999] == "2000\tx"
    assert rows[-1] == "[more: 3000 lines left; continue with offset=2001]"


def test_read_stops_at_the_character_cap_on_a_whole_line_and_continues_from_there(work):
    (work / "wide.txt").write_text("\n".join(f"{i:04d}" + "y" * 96 for i in range(1, 1001)) + "\n")

    first = mini.run_tool("read", {"path": "wide.txt"}, work)
    offset = int(first.rsplit("offset=", 1)[1].rstrip("]"))
    second = mini.run_tool("read", {"path": "wide.txt", "offset": offset}, work)

    assert len(first) <= mini.MAX_OUT + 100
    last_row = first.splitlines()[-2]
    assert last_row == f"{offset - 1}\t{offset - 1:04d}" + "y" * 96
    assert second.splitlines()[0] == f"{offset}\t{offset:04d}" + "y" * 96


def test_read_limit_is_clamped_to_2000_lines_and_a_past_end_offset_is_an_error(work):
    (work / "big.txt").write_text("\n".join("x" for _ in range(5000)) + "\n")

    out = mini.run_tool("read", {"path": "big.txt", "limit": 4000}, work)
    past = mini.run_tool("read", {"path": "big.txt", "offset": 9000}, work)

    assert out.splitlines()[-1].endswith("continue with offset=2001]")
    assert past == "error: offset 9000 is past the end of big.txt (5000 lines)"


def test_a_line_longer_than_the_cap_is_marked_as_cut(work):
    (work / "one.txt").write_text("k" * 30000 + "TAIL\n")

    out = mini.run_tool("read", {"path": "one.txt"}, work)

    assert "[line cut: 30004 chars" in out and "TAIL" not in out


def test_paths_outside_the_work_folder_are_refused(work):
    with pytest.raises(ValueError, match="outside the work folder"):
        mini.run_tool("read", {"path": "/etc/hostname"}, work)


# --- bash -------------------------------------------------------------------------------------

def test_short_command_output_is_returned_whole(work):
    assert mini.run_tool("bash", {"command": "echo hi"}, work) == "exit 0\nhi\n"


def test_long_output_keeps_its_first_50_lines_a_cut_note_and_its_end(work):
    out = mini.run_tool("bash", {"command": "seq 1 10000"}, work)

    rows = out.splitlines()
    assert rows[:3] == ["exit 0", "1", "2"] and rows[49] == "49"
    assert rows[50].startswith("...[cut ") and rows[-1] == "10000"
    assert len(out) <= mini.MAX_OUT


def test_wide_first_lines_keep_whole_lines_within_a_quarter_and_the_cut_count_is_right(work):
    out = mini.run_tool("bash", {"command": "for i in $(seq 1 1000); do printf 'L%d %0200d\\n' $i 0; done"}, work)

    rows = out.splitlines()
    note = next(r for r in rows if r.startswith("...[cut "))
    head = rows[:rows.index(note)]
    tail = rows[rows.index(note) + 1:]
    assert len("\n".join(head)) <= mini.MAX_OUT // 4
    assert all(r == "exit 0" or r.endswith("0" * 200) for r in head)
    assert note == f"...[cut {1000 + 1 - len(head) - len(tail)} lines]..."
    assert tail[-1].startswith("L1000 ") and len(out) <= mini.MAX_OUT


def test_a_few_wide_lines_still_keep_the_summary_line_at_the_end(work):
    cmd = "for i in $(seq 1 9); do printf '%03000d\\n' 0; done; echo 'FAILED 3 passed'"
    out = mini.run_tool("bash", {"command": cmd}, work)

    assert out.splitlines()[-1] == "FAILED 3 passed" and len(out) <= mini.MAX_OUT


def test_a_single_huge_line_keeps_its_start_and_its_end(work):
    cmd = "python3 -c 'print(\"S\" + \"z\" * 100000 + \"END\")'"
    out = mini.run_tool("bash", {"command": cmd}, work)

    rows = out.splitlines()
    assert rows[0] == "exit 0" and rows[1].startswith("Szzz") and "[cut" in out
    assert rows[-1].endswith("zEND") and len(out) <= mini.MAX_OUT


# --- prompt and main loop ---------------------------------------------------------------------

def test_the_system_prompt_lists_the_four_tools():
    for name in ("bash", "read", "edit", "write"):
        assert f"- {name}:" in mini.SYSTEM


def reply(content="done", tool_calls=None, prompt_tokens=123):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(prompt_tokens=prompt_tokens))


class FakeClient:
    def __init__(self, result, client_kwargs):
        self.result, self.client_kwargs, self.calls = result, client_kwargs, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def run_main(monkeypatch, tmp_path, result):
    log = tmp_path / "transcript.jsonl"
    made = {}

    def fake_openai(**kwargs):
        made["client"] = FakeClient(result, kwargs)
        return made["client"]

    monkeypatch.setattr(mini, "LOG", str(log))
    monkeypatch.setenv("LITELLM_KEY", "dummy")
    monkeypatch.setattr(mini, "OpenAI", fake_openai)
    rc = mini.main("do the task")
    return rc, [json.loads(line) for line in log.read_text().splitlines()], made["client"]


def test_a_plain_reply_ends_the_run_and_logs_prompt_tokens(monkeypatch, tmp_path):
    rc, log, client = run_main(monkeypatch, tmp_path, reply(prompt_tokens=4321))

    assert rc == 0 and log[0]["prompt_tokens"] == 4321 and log[0]["calls"] == []
    assert client.client_kwargs["max_retries"] == 6
    assert client.calls[0]["temperature"] == 0.7 and client.calls[0]["max_tokens"] == 8000


def test_a_model_call_error_is_logged_as_the_stop_cause(monkeypatch, tmp_path):
    err = openai.APIConnectionError(request=None)

    rc, log, _ = run_main(monkeypatch, tmp_path, err)

    assert rc == 1 and log[-1]["stopped"].startswith("api error: ")
