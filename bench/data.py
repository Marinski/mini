"""Pinned inputs for the code-context, HumanEval and FinQA suites.

Datasets are not committed (they are large and have their own licences); run
``python bench/data/setup.py`` once to fetch them under ``bench/data/``:

* three.js at a fixed tag (MIT)      -> ``three.module.js``
* openai/human-eval (MIT)            -> ``human_eval.jsonl``
* czyssrs/FinQA (MIT)                -> ``finqa/``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

THREE_JS_TAG = "r150"
THREE_JS_FILE = "three.module.js"


class DataMissing(RuntimeError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"{path} is missing; run: python bench/data/setup.py"
        )


def data_dir() -> Path:
    return DATA_DIR


def require(path: Path) -> Path:
    if not Path(path).exists():
        raise DataMissing(Path(path))
    return Path(path)


@dataclass
class Context:
    """Everything a suite's ``build`` may need beyond its own code."""

    three_js_lines: list[str] | None = None
    human_eval: list[dict] | None = None
    finqa: list[dict] | None = None


def three_js_lines() -> list[str]:
    path = require(DATA_DIR / THREE_JS_FILE)
    return path.read_text().splitlines()


def human_eval_problems() -> list[dict]:
    import json

    path = require(DATA_DIR / "human_eval.jsonl")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def finqa_examples() -> list[dict]:
    import json

    path = require(DATA_DIR / "finqa" / "dev.json")
    return json.loads(path.read_text())
