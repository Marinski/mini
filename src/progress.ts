// Loop breaker: notice when the agent keeps working without changing any file, and say so.
// In the trials, healthy runs never went more than 5 tool calls without a file change after
// their first edit; runs stuck re-checking a finished fix (usually debugging their own wrong
// test) went 10 to 49.
import { createHash } from "node:crypto";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SKIP = new Set([".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"]);
const MAX_FILES = 20_000;

/** A fingerprint of the work folder's files (path, size, mtime); null if it has too many files. */
export function fingerprint(work: string): string | null {
  const h = createHash("sha1");
  let n = 0;
  const walk = (dir: string): boolean => {
    let names: string[];
    try {
      names = readdirSync(dir).sort();
    } catch {
      return true;
    }
    for (const name of names) {
      if (SKIP.has(name)) continue;
      const p = join(dir, name);
      let st;
      try {
        st = statSync(p, { throwIfNoEntry: false });
      } catch {
        continue;
      }
      if (!st) continue;
      if (st.isDirectory()) {
        if (!walk(p)) return false;
      } else if (st.isFile()) {
        if (++n > MAX_FILES) return false;
        h.update(`${p}\0${st.size}\0${st.mtimeMs}\n`);
      }
    }
    return true;
  };
  return walk(work) ? h.digest("hex") : null;
}

export const nudgeText = (calls: number, strong: boolean) => strong
  ? `[harness] ${calls} tool calls without changing any file. Finish now: make the one change that ` +
    "is still needed, or reply with your summary."
  : `[harness] Your last ${calls} tool calls changed no files. Pause and re-read the task and your ` +
    "checklist. If what fails is a test you wrote, check whether the test itself is wrong. If every " +
    "requirement is met and the project's tests pass, stop and reply with a summary.";

/** Counts tool calls since the last file change, starting after the first change (exploring
 * before the first edit is normal). Returns a nudge at `after` calls, then a stronger one every
 * 2 × `after` calls. `after` = 0 turns it off. */
export class Progress {
  private work: string;
  private after: number;
  private last: string | null;
  private changed = false;
  private idle = 0;

  constructor(work: string, after: number) {
    this.work = work;
    this.after = after;
    this.last = after ? fingerprint(work) : null;
  }

  afterTool(): string | null {
    if (!this.after) return null;
    const now = fingerprint(this.work);
    if (now === null) return null; // too big to watch
    if (now !== this.last) {
      this.last = now;
      this.changed = true;
      this.idle = 0;
      return null;
    }
    if (!this.changed) return null;
    this.idle++;
    if (this.idle === this.after) return nudgeText(this.idle, false);
    if (this.idle % (2 * this.after) === 0) return nudgeText(this.idle, true);
    return null;
  }
}
