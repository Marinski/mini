#!/usr/bin/env python3
"""Fetch the pinned inputs for the code-context, HumanEval and FinQA suites.

Idempotent: skips files that already exist unless ``--force`` is given.

    python bench/data/setup.py [--force]

Sources (all permissive):
* three.js r150 ``build/three.module.js``  (MIT)
* openai/human-eval ``data/HumanEval.jsonl`` (MIT)
* czyssrs/FinQA ``dataset/test.json``      (MIT)
"""

from __future__ import annotations

import argparse
import gzip
import sys
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent

SOURCES = [
    (
        "https://raw.githubusercontent.com/mrdoob/three.js/r150/build/three.module.js",
        DATA_DIR / "three.module.js",
        False,
    ),
    (
        "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz",
        DATA_DIR / "human_eval.jsonl",
        True,
    ),
    (
        "https://raw.githubusercontent.com/czyssrs/FinQA/master/dataset/test.json",
        DATA_DIR / "finqa" / "test.json",
        False,
    ),
]


def fetch(url: str, dest: Path, force: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  have {dest.relative_to(DATA_DIR.parent.parent)} ({dest.stat().st_size} bytes)")
        return
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = response.read()
    if url.endswith(".gz"):
        raw = gzip.decompress(raw)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    print(f"  wrote {dest.relative_to(DATA_DIR.parent.parent)} ({len(raw)} bytes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    for url, dest, _ in SOURCES:
        fetch(url, dest, args.force)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
