"""Read/write run records and the append-only index.

Output layout::

    results/bench/<run-id>.json    one file per run, every sub-job
    results/bench/index.jsonl      one line per run, the summary
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "x"


def make_run_id(suite: str, profile: str, model: str, started_at: str) -> str:
    stamp = started_at.replace(":", "").replace("-", "").split("+")[0]
    return f"{slug(suite)}__{slug(profile)}__{slug(model)}__{stamp}"


def summarize(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    subs = [s for job in jobs for s in job["sub_jobs"]]
    counts = {status: 0 for status in ("pass", "fail", "error", "skipped", "ok")}
    for sub in subs:
        counts[sub["status"]] = counts.get(sub["status"], 0) + 1
    ttfts = [s["ttft_seconds"] for s in subs if s["ttft_seconds"] is not None]
    tps = [s["tokens_per_second"] for s in subs if s["tokens_per_second"] is not None]
    cached = [s["cached_tokens"] for s in subs if s["cached_tokens"] is not None]
    checked = counts["pass"] + counts["fail"]
    return {
        "jobs": len(jobs),
        "sub_jobs": len(subs),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "pass_rate": (counts["pass"] / checked) if checked else None,
        "median_ttft_seconds": statistics.median(ttfts) if ttfts else None,
        "median_tokens_per_second": statistics.median(tps) if tps else None,
        "median_cached_tokens": statistics.median(cached) if cached else None,
    }


def write_run(results_dir: Path, run: dict[str, Any]) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{run['run_id']}.json"
    path.write_text(json.dumps(run, indent=2) + "\n")
    return path


def append_index(results_dir: Path, run: dict[str, Any]) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "index.jsonl"
    line = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run["run_id"],
        "suite": run["suite"],
        "profile": run["profile"],
        "model": run["model"],
        "endpoint": run["endpoint"],
        "params": run["params"],
        "context_window": run["context_window"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "summary": run["summary"],
    }
    with path.open("a") as handle:
        handle.write(json.dumps(line) + "\n")
    return path


def load_run(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def iter_index(results_dir: Path) -> Iterator[dict[str, Any]]:
    path = Path(results_dir) / "index.jsonl"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def find_run(results_dir: Path, run_id: str) -> Path:
    direct = Path(results_dir) / f"{run_id}.json"
    if direct.exists():
        return direct
    matches = sorted(Path(results_dir).glob(f"{run_id}*.json"))
    if not matches:
        raise FileNotFoundError(f"no run matching {run_id!r} in {results_dir}")
    return matches[-1]
