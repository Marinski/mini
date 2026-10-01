#!/bin/bash
# Build the trial data folder: the task bases, the offline node_modules (t8) and the grading venv.
# Usage: setup.sh            (idempotent; rebuilds the bases, keeps the venv and deps if they work)
# Data goes to $TRIAL_DATA (default ~/agent-trials), never into this repo: runs write there.
# Tasks (and their TASK.md) come from $TRIAL_TASKS (default $TRIAL_DATA/tasks), which is private.
set -euo pipefail
KIT=$(cd "$(dirname "$0")" && pwd)
DATA=${TRIAL_DATA:-$HOME/agent-trials}
TASKS=${TRIAL_TASKS:-$DATA/tasks}
CONTENT=${CONTENT_PIPELINE_REPO:-$HOME/repos/content-pipeline}
FUNNEL=${FUNNEL_PIPELINE_REPO:-$HOME/repos/funnel-pipeline}
AGENTPIPE=${AGENTPIPE_SOURCE_REPO:-$HOME/repos/agentpipe}
MTBACKTEST=${MT_BACKTEST_REPO:-$HOME/apps/mt-backtest-manager}
T1_SHA=ee6994fc6168924be1bd633e62e16229d9b42bea   # content-pipeline, the parent of fix 34fe079
T2_SHA=849b9b6dffd3edef1aa6c1c637728ab168c5744f   # funnel-pipeline
T8_SHA=333a7b5969f9a965d3fccefee7f9f34e39f37e46   # mt-backtest-manager, the parent of fix 6d4cb6c
T9_SHA=7b2acb9fdbee41fb9c9dbf2574725ba352f68aaa   # agentpipe, the parent of fix 7e025f3
mkdir -p "$DATA/bases" "$DATA/deps"

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
base t8 "$MTBACKTEST" "$T8_SHA"
base t9 "$AGENTPIPE" "$T9_SHA"
# T6 = T2's base plus one maintainer commit that plants the trap comment in config.py.
rm -rf "$DATA/bases/t6"
git clone -q "$DATA/bases/t2" "$DATA/bases/t6"
(cd "$DATA/bases/t6" && python3 "$TASKS/t6/plant_trap.py" &&
	git -c user.email=maint@local -c user.name=maintainer commit -qam "config: CI notes")
prune "$DATA/bases/t6" "$(git -C "$DATA/bases/t6" rev-parse HEAD)"

# The fix commit each base must not be able to reach.
declare -A FIX=( [t1]=34fe07919a8d23e8b757772fde02d873d1aa070f [t8]=6d4cb6c117524bd3608133cb69345af82d684547 [t9]=7e025f3101a002498ba0c2d3a0fc677644ad8b6c )
for t in t1 t2 t6 t8 t9; do
	git -C "$DATA/bases/$t" rev-parse HEAD > "$DATA/bases/$t.sha"
	if [ -n "${FIX[$t]:-}" ] && git -C "$DATA/bases/$t" cat-file -e "${FIX[$t]}" 2>/dev/null; then
		echo "setup: the $t fix commit ${FIX[$t]} leaked into base $t" >&2; exit 1
	fi
	echo "base $t: $(git -C "$DATA/bases/$t" log -1 --format='%h %s') ($(git -C "$DATA/bases/$t" rev-list --all | wc -l) commits)"
done

# T8's node_modules, mounted read-only at run time so vitest cannot write to it. Built once from
# the lockfile; it pulls the private ats-ui from Bitbucket, so it needs the machine's git access.
if [ ! -x "$DATA/deps/t8/node_modules/.bin/vitest" ]; then
	echo "setup: building $DATA/deps/t8/node_modules (npm ci, needs Bitbucket access for ats-ui)"
	tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
	cp -a "$DATA/bases/t8/frontend/." "$tmp/"
	(cd "$tmp" && npm ci --no-audit --no-fund --cache "$DATA/npm-cache" >/dev/null)
	mkdir -p "$DATA/deps/t8"; mv "$tmp/node_modules" "$DATA/deps/t8/node_modules"
fi
echo "t8 deps: $(ls "$DATA/deps/t8/node_modules" | wc -l) packages, vitest $("$DATA/deps/t8/node_modules/.bin/vitest" --version)"

# Grading venv: funnel-pipeline's requirements plus pytest (content-pipeline's tests need nothing
# more) and t9's imports: agentpipe_runner.db pulls psycopg, the config loader pulls dotenv.
if ! "$DATA/venv/bin/python" -c "import pytest, psycopg, dotenv" 2>/dev/null; then
	uv venv -q "$DATA/venv" --python 3.12
	VIRTUAL_ENV="$DATA/venv" uv pip install -q -r "$DATA/bases/t2/requirements.txt" pytest "psycopg[binary]" python-dotenv
fi
echo "venv: $("$DATA/venv/bin/python" -m pytest --version 2>&1), $("$DATA/venv/bin/python" -c 'import psycopg, dotenv; print("psycopg + dotenv ok")')"
