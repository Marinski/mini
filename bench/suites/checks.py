"""Small, shared answer-normalising helpers for suite checks."""

from __future__ import annotations

import re

_REFUSAL = re.compile(
    r"\b(i don'?t know|i do not know|sorry|cannot|can'?t|unable to|as an ai)\b",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def first_line(text: str) -> str:
    return normalize((text or "").strip().splitlines()[0] if (text or "").strip() else "")


def strip_markdown(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def yes_no(text: str) -> str | None:
    """Return 'yes', 'no' or None for a one-word yes/no answer."""
    word = re.sub(r"[^A-Za-z]", "", first_line(text)).lower()
    if word in ("yes", "no"):
        return word
    return None


def ints(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"-?\d+", text or "")]


def find_number_groups(text: str) -> list[str]:
    """Runs of digits of any length, in order."""
    return re.findall(r"\d+", text or "")


def find_digit_runs(text: str, length: int) -> list[str]:
    return [run for run in re.findall(rf"\d{{{length}}}", text or "")]


def is_identifier(text: str) -> bool:
    """A plausible model-identifier string: short, non-empty, not a refusal."""
    value = first_line(text)
    if not value or len(value) > 120:
        return False
    if _REFUSAL.search(value):
        return False
    return bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"\d", value))


def numbers_equal(answer: str, expected: int) -> bool:
    found = ints(strip_markdown(answer))
    return bool(found) and found[0] == expected
