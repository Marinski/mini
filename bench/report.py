"""Turn run records into the per-model Markdown tables used on the wiki.

One table per model, one row per benchmark: pass rate, median TTFT and tok/s —
the same three columns Protorikis's Results page shows, so the agent-trial
numbers and the bench numbers read together.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

COLUMNS = ("Benchmark", "Pass rate", "Passed", "Median TTFT (s)", "Tokens/s", "Context")


def latest_per_model_suite(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["model"], record["suite"])
        current = latest.get(key)
        if current is None or record.get("started_at", "") >= current.get("started_at", ""):
            latest[key] = record
    return list(latest.values())


def _pass_rate(summary: dict[str, Any]) -> str:
    rate = summary.get("pass_rate")
    return "—" if rate is None else f"{rate * 100:.0f}%"


def _passed(summary: dict[str, Any]) -> str:
    checked = summary.get("passed", 0) + summary.get("failed", 0)
    return f"{summary.get('passed', 0)}/{checked}"


def _number(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _context(record: dict[str, Any]) -> str:
    window = record.get("context_window")
    return "—" if window is None else str(window)


def render_model_table(model: str, records: list[dict[str, Any]]) -> str:
    rows = sorted(records, key=lambda r: r["suite"])
    lines = [f"### {model}", "", "| " + " | ".join(COLUMNS) + " |"]
    lines.append("|" + "|".join(["---"] * len(COLUMNS)) + "|")
    for record in rows:
        summary = record["summary"]
        lines.append(
            "| "
            + " | ".join(
                [
                    record["suite"],
                    _pass_rate(summary),
                    _passed(summary),
                    _number(summary.get("median_ttft_seconds")),
                    _number(summary.get("median_tokens_per_second")),
                    _context(record),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def render(records: Iterable[dict[str, Any]], title: str = "mini bench results") -> str:
    picked = latest_per_model_suite(records)
    if not picked:
        return f"# {title}\n\nNo runs yet.\n"
    models = sorted({r["model"] for r in picked})
    parts = [f"# {title}", ""]
    for model in models:
        parts.append(render_model_table(model, [r for r in picked if r["model"] == model]))
        parts.append("")
    parts.append(
        "Pass rate counts checked prompts only (errors and context skips are "
        "excluded). Median TTFT and tok/s are per prompt across the run."
    )
    return "\n".join(parts) + "\n"
