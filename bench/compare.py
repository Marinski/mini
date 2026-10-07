"""Compare two runs: summary side by side, and pass/fail agreement per prompt.

Used for the step-9 parity check (our run vs a Protorikis run) and for
comparing two models or two profiles. Agreement counts only prompts both runs
actually checked (pass/fail); errors and skips are not agreement.
"""

from __future__ import annotations

from typing import Any

METRICS = (
    ("sub_jobs", "sub-jobs"),
    ("passed", "passed"),
    ("failed", "failed"),
    ("errors", "errors"),
    ("skipped", "skipped"),
    ("pass_rate", "pass rate"),
    ("median_ttft_seconds", "median TTFT (s)"),
    ("median_tokens_per_second", "tokens/s"),
)


def _keyed(run: dict[str, Any]) -> dict[tuple[str, str], str]:
    out = {}
    for job in run["jobs"]:
        for sub in job["sub_jobs"]:
            out[(job["job_id"], sub["label"])] = sub["status"]
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or not b:
        return None
    return a / b


def _within_10(ratio: float | None) -> bool | None:
    return None if ratio is None else 0.9 <= ratio <= 1.1


def compare_runs(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    sa, sb = a["summary"], b["summary"]
    metrics = [
        {"metric": label, "a": sa.get(key), "b": sb.get(key)} for key, label in METRICS
    ]
    ttft_ratio = _ratio(sa.get("median_ttft_seconds"), sb.get("median_ttft_seconds"))
    tps_ratio = _ratio(sa.get("median_tokens_per_second"), sb.get("median_tokens_per_second"))
    ka, kb = _keyed(a), _keyed(b)
    shared = set(ka) & set(kb)
    comparable = [k for k in shared if ka[k] in ("pass", "fail") and kb[k] in ("pass", "fail")]
    agree = [k for k in comparable if ka[k] == kb[k]]
    disagreements = sorted(k for k in comparable if ka[k] != kb[k])
    return {
        "a": {"run_id": a["run_id"], "model": a["model"], "suite": a["suite"], "profile": a["profile"]},
        "b": {"run_id": b["run_id"], "model": b["model"], "suite": b["suite"], "profile": b["profile"]},
        "metrics": metrics,
        "speed": {
            "ttft_ratio": ttft_ratio,
            "tokens_per_second_ratio": tps_ratio,
            "ttft_within_10pct": _within_10(ttft_ratio),
            "tokens_per_second_within_10pct": _within_10(tps_ratio),
        },
        "agreement": {
            "comparable": len(comparable),
            "agree": len(agree),
            "rate": (len(agree) / len(comparable)) if comparable else None,
            "disagreements": [
                {"job_id": k[0], "label": k[1], "a": ka[k], "b": kb[k]} for k in disagreements
            ],
        },
    }


def render_compare(result: dict[str, Any]) -> str:
    a, b = result["a"], result["b"]
    lines = [
        "# bench compare",
        "",
        f"- A: `{a['run_id']}` ({a['model']} / {a['suite']} / {a['profile']})",
        f"- B: `{b['run_id']}` ({b['model']} / {b['suite']} / {b['profile']})",
        "",
        "| Metric | A | B |",
        "|---|---|---|",
    ]
    for row in result["metrics"]:
        lines.append(f"| {row['metric']} | {_fmt(row['a'])} | {_fmt(row['b'])} |")
    speed = result.get("speed", {})
    lines += ["", "| Speed (A/B) | Ratio | within 10% |", "|---|---|---|"]
    lines.append(
        f"| TTFT | {_fmt(speed.get('ttft_ratio'))} | {speed.get('ttft_within_10pct')} |"
    )
    lines.append(
        "| tokens/s | "
        f"{_fmt(speed.get('tokens_per_second_ratio'))} | "
        f"{speed.get('tokens_per_second_within_10pct')} |"
    )
    agreement = result["agreement"]
    lines += ["", f"**Agreement:** {agreement['agree']}/{agreement['comparable']}", ""]
    if agreement["disagreements"]:
        lines += ["| Job | Prompt | A | B |", "|---|---|---|---|"]
        for row in agreement["disagreements"]:
            lines.append(
                f"| {row['job_id']} | {row['label'][:60]} | {row['a']} | {row['b']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"
