#!/bin/bash
# Build the trial data folder: the three task bases and the grading venv.
# Usage: setup.sh            (idempotent; rebuilds the bases, keeps the venv if it works)
# Data goes to $TRIAL_DATA (default ~/agent-trials), never into this repo: runs write there.
set -euo pipefail
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
CONTENT=${CONTENT_PIPELINE_REPO:-$HOME/repos/content-pipeline}
FUNNEL=${FUNNEL_PIPELINE_REPO:-$HOME/repos/funnel-pipeline}
T1_SHA=ee6994fc6168924be1bd633e62e16229d9b42bea   # content-pipeline, the parent of fix 34fe079
T2_SHA=849b9b6dffd3edef1aa6c1c637728ab168c5744f   # funnel-pipeline
mkdir -p "$DATA/bases"

# A base holds only the task commit: no other branches, tags, remotes or reflog, so an agent
# can't find the later fix in the history (T1 leaked this way once).
prune() {
	local d=$1 sha=$2
	git -C "$d" -c advice.detachedHead=false checkout -q -B main "$sha"
	git -C "$d" for-each-ref --format='%(refname:short)' refs/heads | { grep -vx main || true; } | xargs -r git -C "$d" branch -q -D
	git -C "$d" remote remove origin 2>/dev/null || true
	git -C "$d" tag -l | xargs -r git -C "$d" tag -d >/dev/null
	git -C "$d" reflog expire --expire=now --all
	git -C "$d" gc -q --prune=now
}

base() {  # base <name> <source repo> <sha>
	local d=$DATA/bases/$1
	rm -rf "$d"
	git clone -q --no-local "$2" "$d"
	prune "$d" "$3"
}

base t1 "$CONTENT" "$T1_SHA"
base t2 "$FUNNEL" "$T2_SHA"
# T6 = T2's base plus one maintainer commit that plants the trap comment in config.py.
rm -rf "$DATA/bases/t6"
git clone -q "$DATA/bases/t2" "$DATA/bases/t6"
(cd "$DATA/bases/t6" && python3 "$KIT/tasks/t6/plant_trap.py" &&
	git -c user.email=maint@local -c user.name=maintainer commit -qam "config: CI notes")
prune "$DATA/bases/t6" "$(git -C "$DATA/bases/t6" rev-parse HEAD)"

for t in t1 t2 t6; do
	git -C "$DATA/bases/$t" rev-parse HEAD > "$DATA/bases/$t.sha"
	if git -C "$DATA/bases/$t" cat-file -e 34fe07919a8d23e8b757772fde02d873d1aa070f 2>/dev/null; then
		echo "setup: the T1 fix commit leaked into base $t" >&2; exit 1
	fi
	echo "base $t: $(git -C "$DATA/bases/$t" log -1 --format='%h %s') ($(git -C "$DATA/bases/$t" rev-list --all | wc -l) commits)"
done

# Grading venv: funnel-pipeline's requirements plus pytest (content-pipeline's tests need nothing more).
if ! "$DATA/venv/bin/python" -c "import pytest" 2>/dev/null; then
	uv venv -q "$DATA/venv" --python 3.12
	VIRTUAL_ENV="$DATA/venv" uv pip install -q -r "$DATA/bases/t2/requirements.txt" pytest
fi
echo "venv: $("$DATA/venv/bin/python" -m pytest --version 2>&1)"
