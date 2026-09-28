// The four tools (bash / read / edit / write) and the system prompt: a line-for-line port of
// mini_harness_v2.py, so the TypeScript and Python versions behave the same run for run.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { constants } from "node:os";
import { basename, dirname, join, resolve, sep } from "node:path";
import { structuredPatch } from "diff";

export const MAX_STEPS = 60, BUDGET_S = 2640, MAX_OUT = 20_000;
export const READ_LINES = 2000, HEAD_LINES = 50, DIFF_MAX = 1500;

export const system = (work: string) => `You are a coding agent working in ${work}. You help by reading files, running \
commands, editing code and writing new files.

Tools:
- bash: run a shell command in the work folder (ls, rg, find, tests). Long output keeps its \
first 50 lines and its end.
- read: read a file with line numbers, up to 2000 lines per call; a note says where to continue.
- edit: exact text replacement in one file; several places per call via edits[].
- write: create a new file or replace a whole file.

Guidelines:
- Explore with bash (ls, rg, find) before changing code, and read a file before editing it.
- Put all changes to one file in one edit call. Keep each edits[].old as small as possible \
while still matching exactly once in the original file; do not let edits overlap.
- Use write only for new files or complete rewrites.
- Make minimal changes that do what the task asks, and nothing else.
- Run the project's tests before you finish, then reply without a tool call.`;

const fn = (name: string, description: string, properties: object, required: string[]) =>
  ({ type: "function" as const, function: { name, description, parameters: { type: "object", properties, required } } });

const S = { type: "string" };
const EDIT = { type: "object", properties: { old: S, new: S }, required: ["old", "new"] };
export const TOOLS = [
  fn("bash", "Run a shell command in the work folder.", { command: S }, ["command"]),
  fn("read", "Read a text file with line numbers, up to 2000 lines per call.",
    { path: S, offset: { type: "integer" }, limit: { type: "integer" } }, ["path"]),
  fn("edit", "Replace exact text in one file. Each edits[].old must match exactly once in the " +
    "original file; edits must not overlap.", { path: S, edits: { type: "array", items: EDIT } }, ["path", "edits"]),
  fn("write", "Create or overwrite a whole file.", { path: S, content: S }, ["path", "content"]),
];

type Args = Record<string, unknown>;

// Python's str.splitlines(): the same line breaks, and no empty last item for a final newline.
const BREAK = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;
export function splitLines(text: string): string[] {
  if (!text) return [];
  const lines = text.split(BREAK);
  if (BREAK.test(text.at(-1)!)) lines.pop();
  return lines;
}

// Like splitLines, but each line keeps its line break (Python's splitlines(True)).
function splitKeep(text: string): string[] {
  return text.match(/[^\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]*(?:\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]|$)/g)!
    .filter((l) => l !== "");
}

function need(a: Args, key: string): string {
  if (!(key in a)) throw new Error(`'${key}'`);
  return String(a[key]);
}

function toInt(v: unknown, dflt: number): number {
  if (v === undefined || v === null || v === 0 || v === "" || v === false) return dflt;
  const n = typeof v === "number" ? Math.trunc(v) : Number.parseInt(String(v).trim(), 10);
  if (Number.isNaN(n) || (typeof v === "string" && !/^\s*[+-]?\d+\s*$/.test(v))) {
    throw new Error(`invalid literal for int() with base 10: '${v}'`);
  }
  return n;
}

// Resolve like pathlib's resolve(): follow symlinks in the part of the path that exists.
function realish(p: string): string {
  let head = resolve(p);
  const rest: string[] = [];
  while (!existsSync(head) && dirname(head) !== head) {
    rest.unshift(basename(head));
    head = dirname(head);
  }
  return join(realpathSync(head), ...rest);
}

export function inside(p: string, work: string): string {
  const path = realish(resolve(work, p));
  if (path !== work && !path.startsWith(work.endsWith(sep) ? work : work + sep)) {
    throw new Error(`${p} is outside the work folder`);
  }
  return path;
}

/** Fit text in MAX_OUT: up to HEAD_LINES whole lines (a quarter of the room at most), a note,
 * then as many whole last lines as fit. A line longer than the head's room keeps its start in
 * the head; a last line too long for the tail keeps its end. Both are marked with "…". */
export function cutLines(text: string): string {
  if (text.length <= MAX_OUT) return text;
  const lines = splitLines(text);
  const quarter = Math.floor(MAX_OUT / 4);
  const head: string[] = [];
  let size = 0;
  for (const line of lines.slice(0, HEAD_LINES)) {
    if (size + line.length + 1 > quarter) {
      if (line.length > quarter) {
        head.push(line.slice(0, quarter - size) + "…");
        size = quarter + 2;
      }
      break;
    }
    head.push(line);
    size += line.length + 1;
  }
  let room = MAX_OUT - size - 40;
  const tail: string[] = [];
  for (let i = lines.length - 1; i >= head.length; i--) {
    if (lines[i].length + 1 > room) break;
    tail.unshift(lines[i]);
    room -= lines[i].length + 1;
  }
  if (!tail.length) tail.push("…" + lines.at(-1)!.slice(-Math.max(room - 1, 1)));
  const skipped = Math.max(lines.length - head.length - tail.length, 0);
  const note = skipped ? `...[cut ${skipped} lines]...` : "...[cut inside a long line]...";
  return [...head, note, ...tail].join("\n");
}

function read(a: Args, work: string): string {
  const lines = splitLines(readFileSync(inside(need(a, "path"), work), "utf8"));
  const start = Math.max(toInt(a.offset, 1), 1);
  if (lines.length && start > lines.length) {
    return `error: offset ${start} is past the end of ${a.path} (${lines.length} lines)`;
  }
  const limit = Math.min(Math.max(toInt(a.limit, READ_LINES), 1), READ_LINES);
  let end = Math.min(start - 1 + limit, lines.length);
  const rows: string[] = [];
  let size = 0;
  for (let i = start; i <= end; i++) {
    let row = `${i}\t${lines[i - 1]}`;
    if (row.length > MAX_OUT) {
      row = row.slice(0, MAX_OUT) + ` …[line cut: ${lines[i - 1].length} chars; use bash to see all]`;
    }
    if (rows.length && size + row.length + 1 > MAX_OUT) {
      end = i - 1;
      break;
    }
    rows.push(row);
    size += row.length + 1;
  }
  if (end < lines.length) rows.push(`[more: ${lines.length - end} lines left; continue with offset=${end + 1}]`);
  return rows.join("\n");
}

const count = (text: string, sub: string) => text.split(sub).length - 1;

// A unified diff in difflib's format: "--- a\n+++ b\n@@ -2,7 +2,7 @@", 3 context lines.
function unifiedDiff(path: string, before: string, after: string): string {
  if (before === after) return "";
  const range = (start: number, len: number) =>
    len === 1 ? `${start}` : len === 0 ? `${start},0` : `${start},${len}`;
  const out = [`--- ${path}`, `+++ ${path}`];
  for (const h of structuredPatch(path, path, before, after, "", "", { context: 3 }).hunks) {
    out.push(`@@ -${range(h.oldStart, h.oldLines)} +${range(h.newStart, h.newLines)} @@`);
    out.push(...h.lines.filter((l) => !l.startsWith("\\")));
  }
  return out.join("\n") + "\n";
}

function edit(a: Args, work: string): string {
  let edits = a.edits as unknown;
  if (typeof edits === "string") edits = JSON.parse(edits);
  if (edits && typeof edits === "object" && !Array.isArray(edits)) edits = [edits];
  if ((edits === undefined || edits === null) && "old" in a) edits = [{ old: a.old, new: a.new }];
  if (!Array.isArray(edits) || !edits.length) return "error: edits must hold at least one {old, new} pair.";
  const path = need(a, "path");
  const p = inside(path, work);
  const text = readFileSync(p, "utf8");
  const spans: [number, number, string, number][] = [];
  for (const [k, e] of edits.entries()) {
    const i = k + 1;
    if (!(e && typeof e === "object" && typeof e.old === "string" && typeof e.new === "string")) {
      return `error: edit ${i} needs 'old' and 'new' strings. Nothing was changed.`;
    }
    if (!e.old) return `error: edit ${i}: 'old' is empty. Nothing was changed.`;
    const n = count(text, e.old);
    if (n !== 1) {
      return `error: edit ${i}: 'old' found ${n} times in ${path}; it must match exactly ` +
        "once. Nothing was changed. Read the file and retry.";
    }
    const start = text.indexOf(e.old);
    spans.push([start, start + e.old.length, e.new, i]);
  }
  // Same order as Python's tuple sort: start, end, replacement, edit number.
  spans.sort((x, y) => x[0] - y[0] || x[1] - y[1] || (x[2] < y[2] ? -1 : x[2] > y[2] ? 1 : 0) || x[3] - y[3]);
  for (let k = 1; k < spans.length; k++) {
    if (spans[k][0] < spans[k - 1][1]) {
      return `error: edits ${spans[k - 1][3]} and ${spans[k][3]} overlap; merge them into one. Nothing was changed.`;
    }
  }
  let next = text;
  for (const [start, end, repl] of [...spans].reverse()) next = next.slice(0, start) + repl + next.slice(end);
  writeFileSync(p, next);
  // difflib works on lines with their breaks; a last line without one gets "\n" added.
  const diff = unifiedDiff(path, splitKeep(text).join(""), splitKeep(next).join(""));
  return "ok\n" + (diff.length <= DIFF_MAX ? diff : diff.slice(0, DIFF_MAX) + "\n...[diff cut]");
}

function bash(a: Args, work: string): string {
  // The agent's shell: it runs in a container that only mounts its work folder.
  const command = need(a, "command");
  const r = spawnSync("/bin/sh", ["-c", command], { cwd: work, encoding: "utf8", timeout: 300_000, maxBuffer: 1 << 30 });
  if (r.error && (r.error as NodeJS.ErrnoException).code === "ETIMEDOUT") {
    throw new Error(`Command '${command}' timed out after 300 seconds`);
  }
  if (r.error) throw r.error;
  const rc = r.status ?? -(constants.signals[r.signal as keyof typeof constants.signals] ?? 1);
  return cutLines(`exit ${rc}\n${r.stdout}${r.stderr}`);
}

export function runTool(name: string, a: Args, work: string): string {
  if (name === "bash") return bash(a, work);
  if (name === "read") return read(a, work);
  if (name === "edit") return edit(a, work);
  if (name === "write") {
    const p = inside(need(a, "path"), work);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, need(a, "content"));
    return "ok";
  }
  return `error: unknown tool ${name}`;
}
