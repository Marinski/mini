"""bench CLI: run, list, report, compare.

    python bench/bench.py run hello_world --endpoint http://host:8001/v1 --model qwen3.8-27b
    python bench/bench.py list
    python bench/bench.py report
    python bench/bench.py compare <run-a> <run-b>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow: python bench/bench.py ...
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import data
from bench.client import Client
from bench.compare import compare_runs, render_compare
from bench.report import render
from bench.results import find_run, iter_index, load_run
from bench.runner import run as run_suite
from bench.suites import all_suites, get_suite
from bench.suites.base import SubJob


def default_results_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "results" / "bench"


def build_context(suite_id: str, profile: str):
    if suite_id in ("multi_turn_2", "context_caching_1", "memory_recall_1"):
        return data.Context(three_js_lines=data.three_js_lines())
    if suite_id == "human_eval":
        return data.Context(human_eval=data.human_eval_problems())
    if suite_id == "finqa":
        return data.Context(finqa=data.finqa_examples())
    return None


def _status_icon(status: str) -> str:
    return {
        "pass": "ok",
        "fail": "FAIL",
        "error": "ERR",
        "skipped": "skip",
        "ok": "?",
    }.get(status, status)


def _print_subjob(sub: SubJob) -> None:
    bits = [_status_icon(sub.status)]
    if sub.output_tokens is not None:
        bits.append(f"{sub.output_tokens} tok")
    if sub.ttft_seconds is not None:
        bits.append(f"ttft={sub.ttft_seconds:.2f}s")
    if sub.tokens_per_second is not None:
        bits.append(f"{sub.tokens_per_second:.1f} tok/s")
    if sub.cached_tokens:
        bits.append(f"cached={sub.cached_tokens}")
    if sub.reason and sub.status in ("fail", "error", "skipped"):
        bits.append(sub.reason)
    print(f"    {' | '.join(bits)}")


def cmd_run(args: argparse.Namespace) -> int:
    overrides = {}
    if args.thinking is not None:
        overrides["thinking"] = args.thinking
    if args.temperature is not None:
        overrides["temperature"] = args.temperature
    if args.max_tokens is not None:
        overrides["max_tokens"] = args.max_tokens
    if args.multi_turn is not None:
        overrides["multi_turn"] = args.multi_turn
    if args.preserve_thinking:
        overrides["preserve_thinking"] = True

    suite = get_suite(args.suite)
    client = Client(args.endpoint, args.model, api_key=args.api_key, timeout=args.timeout)
    ctx = build_context(suite.id, args.profile)
    results_dir = Path(args.results)

    def on_sub(sub: SubJob) -> None:
        if not args.quiet:
            _print_subjob(sub)

    record = run_suite(
        suite,
        args.profile,
        client,
        overrides=overrides,
        ctx=ctx,
        results_dir=results_dir,
        ctx_override=args.ctx,
        lock=not args.no_lock,
        on_subjob=on_sub,
    )
    summary = record["summary"]
    print(
        f"{record['run_id']}: {summary['passed']}/{summary['passed'] + summary['failed']} "
        f"passed, {summary['errors']} errors, {summary['skipped']} skipped"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    suites = all_suites()
    for suite_id, suite in sorted(suites.items()):
        profiles = "/".join(suite.profiles)
        params = ", ".join(f"{k}={v}" for k, v in suite.default_params.items())
        print(f"{suite_id:20s} profiles={profiles:28s} {params}")
    return 0


def _resolve(identifier: str, results_dir: Path) -> dict:
    path = Path(identifier)
    if path.exists():
        return load_run(path)
    return load_run(find_run(results_dir, identifier))


def cmd_report(args: argparse.Namespace) -> int:
    results_dir = Path(args.results)
    records = list(iter_index(results_dir))
    text = render(records, title=args.title)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    results_dir = Path(args.results)
    a = _resolve(args.a, results_dir)
    b = _resolve(args.b, results_dir)
    print(render_compare(compare_runs(a, b)), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench", description=__doc__)
    parser.set_defaults(func=None)
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run one benchmark against one endpoint")
    run_p.add_argument("suite")
    run_p.add_argument(
        "--endpoint",
        default=os.environ.get("BENCH_ENDPOINT"),
        help="OpenAI-compatible base URL (or $BENCH_ENDPOINT)",
    )
    run_p.add_argument("--model", required=True)
    run_p.add_argument("--profile", default="default")
    run_p.add_argument("--ctx", type=int, default=None, help="context window override")
    run_p.add_argument("--api-key", default=os.environ.get("BENCH_API_KEY"))
    run_p.add_argument("--temperature", type=float, default=None)
    run_p.add_argument("--max-tokens", type=int, default=None)
    run_p.add_argument("--thinking", dest="thinking", action="store_true", default=None)
    run_p.add_argument("--no-thinking", dest="thinking", action="store_false")
    run_p.add_argument("--multi-turn", dest="multi_turn", action="store_true", default=None)
    run_p.add_argument("--no-multi-turn", dest="multi_turn", action="store_false")
    run_p.add_argument("--preserve-thinking", action="store_true")
    run_p.add_argument("--timeout", type=float, default=600.0)
    run_p.add_argument("--results", default=str(default_results_dir()))
    run_p.add_argument("--no-lock", action="store_true", help="skip the per-endpoint lock")
    run_p.add_argument("--quiet", action="store_true")
    run_p.set_defaults(func=cmd_run)

    list_p = sub.add_parser("list", help="list the benchmarks")
    list_p.set_defaults(func=cmd_list)

    report_p = sub.add_parser("report", help="render per-model Markdown tables")
    report_p.add_argument("--results", default=str(default_results_dir()))
    report_p.add_argument("--out", default=None)
    report_p.add_argument("--title", default="mini bench results")
    report_p.set_defaults(func=cmd_report)

    compare_p = sub.add_parser("compare", help="compare two runs (or a run and a Protorikis export)")
    compare_p.add_argument("a")
    compare_p.add_argument("b")
    compare_p.add_argument("--results", default=str(default_results_dir()))
    compare_p.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.func is cmd_run and not args.endpoint:
        parser.error("--endpoint is required (or set $BENCH_ENDPOINT)")
    try:
        return args.func(args)
    except (data.DataMissing, FileNotFoundError, KeyError) as exc:
        print(f"bench: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
