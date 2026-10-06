"""Recorded good and bad answers for the deterministic suites (no model calls)."""

from bench.suites.base import SubJob
from bench.suites.hello_world import HelloWorld
from bench.suites.multi_turn_1 import MultiTurn1
from bench.suites.preserve_thinking_1 import PreserveThinking1


def apply(suite, answers):
    job = suite.build("default", None)[0]
    subs = []
    for i, answer in enumerate(answers):
        response, reasoning = answer if isinstance(answer, tuple) else (answer, "")
        subs.append(
            SubJob(
                label=f"turn{i + 1}",
                prompt="",
                prompt_bytes=0,
                response=response,
                reasoning=reasoning,
            )
        )
    suite.apply_checks(job, subs)
    return subs


def statuses(subs):
    return [s.status for s in subs]


def test_hello_world_good():
    subs = apply(HelloWorld(), ["Qwen3.8-27B", "yes", "yes"])
    assert statuses(subs) == ["pass", "pass", "pass"]


def test_hello_world_bad_model_name():
    subs = apply(HelloWorld(), ["I don't know", "yes", "yes"])
    assert statuses(subs) == ["fail", "pass", "pass"]


def test_hello_world_not_yes_no():
    subs = apply(HelloWorld(), ["Qwen3.8", "maybe", "yes"])
    assert statuses(subs) == ["pass", "fail", "fail"]


def test_hello_world_no_recall():
    subs = apply(HelloWorld(), ["Qwen3.8", "yes", "no"])
    assert statuses(subs) == ["pass", "pass", "fail"]


def test_multi_turn_1_good():
    subs = apply(MultiTurn1(), ["ok", "ok", "333", "1111"])
    assert statuses(subs) == ["pass", "pass", "pass", "pass"]


def test_multi_turn_1_wrong_first():
    subs = apply(MultiTurn1(), ["ok", "ok", "334", "1111"])
    assert statuses(subs)[2] == "fail"


def test_multi_turn_1_wrong_sum():
    subs = apply(MultiTurn1(), ["ok", "ok", "333", "2222"])
    assert statuses(subs)[3] == "fail"


def test_multi_turn_1_ignores_markdown_and_commas():
    subs = apply(MultiTurn1(), ["ok", "ok", "333", "```\n1111\n```"])
    assert statuses(subs)[3] == "pass"


REASONING = "I first considered 12345678901234567890 and then 09876543210987654321."


def test_preserve_thinking_good():
    subs = apply(
        PreserveThinking1(),
        [("12345678901234567890", REASONING), "09876543210987654321"],
    )
    assert statuses(subs) == ["pass", "pass"]


def test_preserve_thinking_leaked_second_number():
    subs = apply(
        PreserveThinking1(),
        [("12345678901234567890 09876543210987654321", REASONING), "09876543210987654321"],
    )
    assert statuses(subs) == ["fail", "pass"]


def test_preserve_thinking_one_number_only():
    subs = apply(PreserveThinking1(), [("123", "only 111"), "111"])
    assert statuses(subs) == ["fail", "fail"]


def test_preserve_thinking_no_recall():
    subs = apply(
        PreserveThinking1(),
        [("12345678901234567890", REASONING), "I don't remember the number"],
    )
    assert statuses(subs) == ["pass", "fail"]
