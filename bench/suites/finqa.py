"""finqa: numerical questions over S&P 500 earnings-report excerpts.

The prompt is the report's text and table plus the question. The check takes
the last number in the model's answer and compares it to the executed
``exe_ans`` within 1% relative, accepting the answer as written, as a percent
(x100) or as a fraction (/100), since FinQA mixes ``27.4%`` with 0.274; yes/no is
exact. Only when ``exe_ans`` is not a number does it fall back to the ``answer``
string, rounded to its precision. Re-grading our saved 7 Oct answers this way
agrees with Protorikis on 1085/1147 prompts (907 vs its 911 passes); the first
version, rounding to the ``answer`` string's units, failed ``14.46`` against
``14%`` and passed 564.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, ClassVar

from bench import data
from bench.suites.base import FAIL, PASS, Check, Job, Prompt, Suite

NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)\s*%?")
PURE_NUMBER = re.compile(r"^\s*-?\$?\s*(?:[\d,]+(?:\.\d+)?|\.\d+)\s*%?\s*$")
UNITS = (("billion", 1e9), ("million", 1e6), ("thousand", 1e3))
REL_TOLERANCE = 1e-2
ABS_TOLERANCE = 1e-5
ANSWER_INSTRUCTION = (
    "Answer with only the final number (or yes/no). Do not explain, and do not "
    "repeat the question."
)


def extract_number(text: str) -> float | None:
    """The last number in the answer, with percent and units normalised."""
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "")
    matches = list(NUMBER.finditer(cleaned))
    if not matches:
        return None
    match = matches[-1]
    token = match.group().strip()
    try:
        if token.endswith("%"):
            return float(token[:-1].strip()) / 100.0
        value = float(token)
    except ValueError:
        return None
    tail = cleaned[match.end() : match.end() + 10].strip().lower()
    for word, scale in UNITS:
        if tail.startswith(word):
            return value * scale
    return value


def is_yes_no(text: str) -> bool:
    return str(text).strip().lower() in ("yes", "no")


def is_pure_number(text: str) -> bool:
    return bool(PURE_NUMBER.match(str(text)))


@dataclass(frozen=True)
class Gold:
    kind: str  # "yes_no" | "number" | "text"
    number: float | None
    digits: int


def gold_reference(answer: object, exe_ans: object) -> Gold:
    """The value to compare a prediction against, with its precision."""
    text = "" if answer is None else str(answer)
    if is_yes_no(text):
        return Gold("yes_no", None, 0)
    if is_pure_number(text):
        return Gold("number", extract_number(text), _decimals(text))
    if isinstance(exe_ans, (int, float)):
        return Gold("number", float(exe_ans), _decimals(str(exe_ans)))
    return Gold("text", None, 0)


def _decimals(text: str) -> int:
    text = text.replace(",", "").replace("$", "").strip().rstrip("%").strip()
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1].rstrip("0")) or len(text.split(".", 1)[1])


def _close(predicted: float, gold: float, digits: int) -> bool:
    if round(predicted, digits) == round(gold, digits):
        return True
    return abs(predicted - gold) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(gold))


def answers_match(response: str, answer: object, exe_ans: object = None) -> bool:
    if is_yes_no("" if answer is None else str(answer)):
        return _yes_no(response) == str(answer).strip().lower()
    if isinstance(exe_ans, (int, float)) and not isinstance(exe_ans, bool):
        candidates = _candidates(response)
        # The rounded answer string itself (``14%`` for 0.14464) also passes.
        stated = _raw_number(str(answer)) if is_pure_number(str(answer)) else None
        return any(
            abs(c - exe_ans) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(exe_ans))
            or (stated is not None and abs(c - stated) <= ABS_TOLERANCE)
            for c in candidates
        )
    gold = gold_reference(answer, None)
    if gold.kind == "text":
        return str(answer).strip().lower() in (response or "").strip().lower()
    predicted = extract_number(response)
    if predicted is None or gold.number is None:
        return False
    return _close(predicted, gold.number, gold.digits)


def _candidates(response: str) -> list[float]:
    """The answer's number as written and with percent/units applied, each also x100 and /100."""
    values = {v for v in (_raw_number(response), extract_number(response)) if v is not None}
    return [c for v in values for c in (v, v * 100, v / 100)]


def _raw_number(text: str) -> float | None:
    matches = list(NUMBER.finditer((text or "").replace(",", "").replace("$", "")))
    if not matches:
        return None
    try:
        return float(matches[-1].group().strip().rstrip("%").strip())
    except ValueError:
        return None


def _yes_no(text: str) -> str | None:
    match = re.match(r"\s*(yes|no)\b", text or "", re.IGNORECASE)
    return match.group(1).lower() if match else None


def format_prompt(example: dict) -> str:
    qa = example["qa"]
    pre = "\n".join(example.get("pre_text") or [])
    post = "\n".join(example.get("post_text") or [])
    table = "\n".join(
        " | ".join(str(cell) for cell in row) for row in (example.get("table") or [])
    )
    parts = [part for part in (pre, table, post) if part]
    return "\n\n".join(parts) + f"\n\nQuestion: {qa['question']}\n{ANSWER_INSTRUCTION}"


class FinQA(Suite):
    id = "finqa"
    profiles = ("default",)
    # As Protorikis sends it (7 Oct 2026): only temperature 0, so rikis leaves thinking on.
    default_params: ClassVar[dict[str, Any]] = {"multi_turn": False, "thinking": True, "temperature": 0.0}

    def build(self, profile, ctx):
        examples = getattr(ctx, "finqa", None) or data.finqa_examples()
        jobs = []
        for i, example in enumerate(examples):
            qa = example["qa"]
            jobs.append(
                Job(
                    id=f"finqa-{i}",
                    prompts=[Prompt(qa["question"], format_prompt(example))],
                    params=dict(self.default_params),
                    meta={"answer": qa.get("answer"), "exe_ans": qa.get("exe_ans")},
                )
            )
        return jobs

    def check(self, job, subjobs):
        answer = job.meta["answer"]
        exe_ans = job.meta["exe_ans"]
        results = []
        for sub in subjobs:
            if answers_match(sub.response, answer, exe_ans):
                results.append(Check(PASS))
            else:
                results.append(
                    Check(FAIL, f"expected {answer!r}, got {_last_line(sub.response)!r}")
                )
        return results


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:80] if lines else ""
