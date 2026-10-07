"""Run HumanEval completions in a throwaway, network-less Docker container.

One container per batch: the programs and a driver are written to a temporary
directory, mounted read-only at ``/problem``, and run there with CPU and memory
caps and a per-problem timeout. ``local_runner`` runs the same programs in the
current interpreter and exists only for the trusted self-check (canonical
solutions), never for model output at run time.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent / "sandbox"
RUN_ALL = SANDBOX / "run_all.py"
DEFAULT_IMAGE = "mini-bench-humaneval:1"
PER_PROBLEM_TIMEOUT = 10

Runner = Callable[..., dict[str, str]]


def extract_body(prompt: str, response: str) -> str:
    """The completion to append to ``prompt``, indentation preserved.

    Strips code fences, and if the model echoed the signature + docstring the
    prompt is removed so it is not duplicated.
    """
    code = response or ""
    code = re.sub(r"^\s*```[a-zA-Z0-9]*[ \t]*\n?", "", code)
    code = re.sub(r"\n?```\s*$", "", code)
    code = code.strip("\n")
    needle = prompt.strip("\n")
    if needle and needle in code:
        code = code[code.index(needle) + len(needle) :].lstrip("\n")
    return code


def build_program(problem: dict, completion: str) -> str:
    body = extract_body(problem["prompt"], completion)
    return f"{problem['prompt']}{body}\n{problem['test']}\n\ncheck({problem['entry_point']})\n"


def evaluate(programs: dict[str, str], *, runner: Runner | None = None) -> dict[str, str]:
    return (runner or docker_runner)(programs)


def docker_runner(
    programs: dict[str, str],
    *,
    image: str = DEFAULT_IMAGE,
    timeout_per: int = PER_PROBLEM_TIMEOUT,
    timeout: float = 900.0,
) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "run_all.py").write_text(RUN_ALL.read_text())
        for name, code in programs.items():
            (root / f"{name}.py").write_text(code)
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--cpus", "1", "--memory", "512m",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", f"PER_TIMEOUT={timeout_per}",
            "-v", f"{root}:/problem:ro",
            "-w", "/problem",
            image, "python", "run_all.py",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"human-eval container failed: {proc.stderr.strip()[:500]}")
        return _parse(proc.stdout)


def local_runner(
    programs: dict[str, str], *, timeout_per: int = PER_PROBLEM_TIMEOUT
) -> dict[str, str]:
    """Run programs with the current interpreter. Only for trusted self-checks."""
    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, code in programs.items():
            path = Path(tmp) / f"{name}.py"
            path.write_text(code)
            try:
                proc = subprocess.run(
                    [sys.executable, str(path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_per,
                    check=False,
                )
                results[name] = "pass" if proc.returncode == 0 else "fail"
            except subprocess.TimeoutExpired:
                results[name] = "timeout"
    return results


def build_image(image: str = DEFAULT_IMAGE) -> None:
    subprocess.run(["docker", "build", "-t", image, str(SANDBOX)], check=True)


def _parse(stdout: str) -> dict[str, str]:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"no result JSON from human-eval container: {stdout.strip()[:200]}")
