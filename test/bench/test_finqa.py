import pytest

from bench import data
from bench.suites.finqa import (
    FinQA,
    answers_match,
    extract_number,
    format_prompt,
    gold_reference,
    is_pure_number,
)

FINQA = data.DATA_DIR / "finqa" / "test.json"
needs_data = pytest.mark.skipif(not FINQA.exists(), reason="run bench/data/setup.py")


def test_extract_number_normalises_units():
    assert extract_number("$1,234") == 1234.0
    assert extract_number("16.93%") == pytest.approx(0.1693)
    assert extract_number(".9%") == pytest.approx(0.009)
    assert extract_number("-62.5%") == pytest.approx(-0.625)
    assert extract_number("the answer is 42") == 42.0
    assert extract_number("no numbers here") is None
    assert extract_number("") is None


def test_extract_number_takes_the_last():
    assert extract_number("first 10 then 20") == 20.0


def test_is_pure_number():
    assert is_pure_number("127.40")
    assert is_pure_number("$1,234")
    assert is_pure_number("-62.5%")
    assert not is_pure_number("10 .")
    assert not is_pure_number("about 5")
    assert not is_pure_number("")


def test_answers_match_numeric():
    assert answers_match("127.4", "127.40", 127.4)
    assert answers_match("about 94", "94", 94.0)
    assert answers_match("16.93%", "16.93%", 0.1693)
    assert not answers_match("95", "94", 94.0)


def test_answers_match_yes_no_is_exact():
    assert answers_match("yes", "yes", None)
    assert answers_match("yes, it did", "yes", None)
    assert not answers_match("yes", "no", None)


def test_answers_match_falls_back_to_exe_ans():
    # an empty / descriptive gold answer uses the executed value
    assert gold_reference("", 1.1197).kind == "number"
    assert answers_match("1.1197", "", 1.1197)
    assert not answers_match("2.0", "", 1.1197)


def test_extract_number_scales_word_units():
    assert extract_number("411.91 million") == pytest.approx(411_910_000)
    assert extract_number("2 billion") == pytest.approx(2e9)


def test_format_prompt_has_question_and_table():
    example = {
        "pre_text": ["Revenue was $100."],
        "post_text": [],
        "table": [["year", "revenue"], ["2017", "100"]],
        "qa": {"question": "what was revenue in 2017?"},
    }
    prompt = format_prompt(example)
    assert "what was revenue in 2017?" in prompt
    assert "2017 | 100" in prompt


@needs_data
def test_all_1147_gold_answers_pass_the_extractor():
    examples = data.finqa_examples()
    assert len(examples) == 1147
    for example in examples:
        qa = example["qa"]
        answer, exe_ans = qa.get("answer"), qa.get("exe_ans")
        kind = gold_reference(answer, exe_ans).kind
        if kind == "yes_no":
            reference = str(answer)
        elif kind == "number":
            reference = str(answer) if is_pure_number(answer) else str(exe_ans)
        else:
            reference = str(answer)
        assert answers_match(reference, answer, exe_ans), example["id"]


@needs_data
def test_suite_builds_one_job_per_example():
    ctx = data.Context(finqa=data.finqa_examples()[:5])
    jobs = FinQA().build("default", ctx)
    assert len(jobs) == 5
    assert all(len(job.prompts) == 1 for job in jobs)
