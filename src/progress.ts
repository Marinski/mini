// Loop breaker: notice when the agent keeps working without making progress, and say so.
// Two triggers, chosen by mode:
//   - "after" (default): count tool calls since the last file change; nudge at `after` idle
//     calls, stronger at 2 x `after`.
//   - "strike": count identical tool calls in a row (same name and arguments); nudge at
//     `strike` repeats, stronger at 2 x `strike`. It targets the re-run-the-same-command
//     loop without firing on varied work.
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

export const strikeText = (count: number, strong: boolean) => strong
  ? `[harness] The same tool call has now run ${count} times in a row with no change. Finish now: ` +
    "make the one change that is still needed, or reply with your summary."
  : `[harness] You have run the same tool call ${count} times in a row with no change. If it is a ` +
    "test you wrote, the test itself may be wrong. Re-read the task and your checklist, then either " +
    "change your approach or stop and reply with a summary.";

export type NudgeMode = "after" | "strike";

/**
 * Counts how long the agent has worked without progress and returns a nudge when it is stuck.
 *
 * `after` mode counts tool calls since the last file change (starting after the first change:
 * exploring before the first edit is normal) and nudges at `after` calls, then stronger every
 * 2 x `after`. `strike` mode counts identical calls in a row (same `sig`) and nudges at `strike`
 * repeats, stronger every 2 x `strike`. `after` = 0 turns nudging off for both modes.
 */
export class Progress {
  private work: string;
  private after: number;
  private mode: NudgeMode;
  private strike: number;
  private last: string | null;
  private changed = false;
  private idle = 0;
  private streak = 0;
  private lastSig: string | null = null;

  constructor(work: string, after: number, mode: NudgeMode = "after", strike = 3) {
    this.work = work;
    this.after = after;
    this.mode = mode;
    this.strike = Math.max(1, Math.floor(strike)); // 0 would make `streak % strike` NaN
    this.last = after ? fingerprint(work) : null;
  }

  afterTool(sig = ""): string | null {
    if (!this.after) return null;
    const now = fingerprint(this.work);
    if (now === null) return null; // too big to watch
    if (now !== this.last) {
      this.last = now;
      this.changed = true;
      this.idle = 0;
      this.streak = 0;
      this.lastSig = sig;
      return null;
    }
    if (!this.changed) return null;
    if (this.mode === "strike") {
      this.streak = sig === this.lastSig ? this.streak + 1 : 1;
      this.lastSig = sig;
      if (this.streak === this.strike) return strikeText(this.streak, false);
      if (this.streak % (2 * this.strike) === 0) return strikeText(this.streak, true);
      return null;
    }
    this.idle++;
    if (this.idle === this.after) return nudgeText(this.idle, false);
    if (this.idle % (2 * this.after) === 0) return nudgeText(this.idle, true);
    return null;
  }
}
