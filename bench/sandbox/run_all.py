"""Driver run inside the human-eval sandbox: run each ``<name>.py`` with a timeout.

Writes one JSON object to stdout: ``{"<name>": "pass"|"fail"|"timeout"}``.
Program files are trusted only in the sense that the container has no network,
no host mounts but this directory, and capped CPU and memory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    timeout = float(os.environ.get("PER_TIMEOUT", "10"))
    results: dict[str, str] = {}
    for path in sorted(HERE.glob("*.py")):
        if path.name == "run_all.py":
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            results[path.stem] = "pass" if proc.returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            results[path.stem] = "timeout"
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
