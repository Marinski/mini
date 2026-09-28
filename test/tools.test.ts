// Behaviour tests for the tools: the same cases as test_mini_v2.py, so both versions match.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { MAX_OUT, runTool, splitLines, system } from "../src/tools.ts";

const workdir = () => realpathSync(mkdtempSync(join(tmpdir(), "mini-")));
const put = (w: string, f: string, s: string) => writeFileSync(join(w, f), s);
const get = (w: string, f: string) => readFileSync(join(w, f), "utf8");
const edit = (w: string, a: Record<string, unknown>) => runTool("edit", a, w);

// --- edit -------------------------------------------------------------------------------------

test("two disjoint edits apply in one call with a diff for each", () => {
  const w = workdir();
  put(w, "a.py", Array.from({ length: 40 }, (_, i) => `line ${i + 1}`).join("\n") + "\n");
  const out = edit(w, { path: "a.py", edits: [{ old: "line 5\n", new: "FIVE\n" }, { old: "line 30\n", new: "THIRTY\n" }] });
  const text = get(w, "a.py");
  assert.ok(out.startsWith("ok"));
  assert.ok(text.includes("FIVE\n") && text.includes("THIRTY\n") && !text.includes("line 5\n"));
  assert.ok(out.includes("@@ -2,7 +2,7 @@") && out.includes("@@ -27,7 +27,7 @@"), out);
  assert.ok(out.includes("-line 5") && out.includes("+THIRTY"));
});

test("overlapping edits are rejected and the file is unchanged", () => {
  const w = workdir();
  put(w, "a.py", "alpha beta gamma\n");
  const out = edit(w, { path: "a.py", edits: [{ old: "alpha beta", new: "x" }, { old: "beta gamma", new: "y" }] });
  assert.ok(out.startsWith("error") && out.includes("overlap"));
  assert.equal(get(w, "a.py"), "alpha beta gamma\n");
});

for (const [old, n] of [["missing", 0], ["dup", 2]] as const) {
  test(`an edit that matches ${n} times names the edit and changes nothing`, () => {
    const w = workdir();
    put(w, "a.py", "dup\nkeep\ndup\n");
    const out = edit(w, { path: "a.py", edits: [{ old: "keep", new: "KEPT" }, { old, new: "z" }] });
    assert.ok(out.startsWith("error: edit 2") && out.includes(`found ${n} times`), out);
    assert.equal(get(w, "a.py"), "dup\nkeep\ndup\n");
  });
}

test("the v1 old/new shape still works", () => {
  const w = workdir();
  put(w, "a.py", "x = 1\n");
  assert.ok(edit(w, { path: "a.py", old: "x = 1", new: "x = 2" }).startsWith("ok"));
  assert.equal(get(w, "a.py"), "x = 2\n");
});

test("the v1 shape without new is an error, not a deletion", () => {
  const w = workdir();
  put(w, "a.py", "x = 1\n");
  assert.ok(edit(w, { path: "a.py", old: "x = 1" }).startsWith("error: edit 1 needs"));
  assert.equal(get(w, "a.py"), "x = 1\n");
});

for (const edits of [JSON.stringify([{ old: "x = 1", new: "x = 2" }]), { old: "x = 1", new: "x = 2" }]) {
  test(`edits sent as ${typeof edits === "string" ? "a JSON string" : "a single object"} are accepted`, () => {
    const w = workdir();
    put(w, "a.py", "x = 1\n");
    assert.ok(edit(w, { path: "a.py", edits }).startsWith("ok"));
    assert.equal(get(w, "a.py"), "x = 2\n");
  });
}

test("the diff stays readable when the file has no final newline", () => {
  const w = workdir();
  put(w, "a.py", "x = 1");
  const out = edit(w, { path: "a.py", edits: [{ old: "x = 1", new: "x = 2" }] });
  assert.ok(out.includes("-x = 1\n+x = 2\n"), out);
});

for (const [item, message] of [[{ old: "x" }, "needs 'old' and 'new'"], ["x", "needs 'old' and 'new'"],
  [{ old: "", new: "y" }, "'old' is empty"]] as const) {
  test(`a malformed edit (${JSON.stringify(item)}) gets a clear error and changes nothing`, () => {
    const w = workdir();
    put(w, "a.py", "x = 1\n");
    const out = edit(w, { path: "a.py", edits: [item] });
    assert.ok(out.startsWith("error: edit 1") && out.includes(message), out);
    assert.equal(get(w, "a.py"), "x = 1\n");
  });
}

test("a long diff is cut", () => {
  const w = workdir();
  put(w, "a.py", Array.from({ length: 500 }, (_, i) => `v${i} = ${i}`).join("\n") + "\n");
  const out = edit(w, { path: "a.py", edits: [{ old: "v0 = 0\n", new: Array.from({ length: 500 }, (_, i) => `w${i} = ${i}\n`).join("") }] });
  assert.ok(out.startsWith("ok") && out.endsWith("[diff cut]") && out.length < 1600);
});

// --- read -------------------------------------------------------------------------------------

test("read returns 2000 lines and says where to continue", () => {
  const w = workdir();
  put(w, "big.txt", "x\n".repeat(5000));
  const rows = splitLines(runTool("read", { path: "big.txt" }, w));
  assert.equal(rows[0], "1\tx");
  assert.equal(rows[1999], "2000\tx");
  assert.equal(rows.at(-1), "[more: 3000 lines left; continue with offset=2001]");
});

test("read stops at the character cap on a whole line and continues from there", () => {
  const w = workdir();
  const row = (i: number) => String(i).padStart(4, "0") + "y".repeat(96);
  put(w, "wide.txt", Array.from({ length: 1000 }, (_, i) => row(i + 1)).join("\n") + "\n");
  const first = runTool("read", { path: "wide.txt" }, w);
  const offset = Number(first.split("offset=").at(-1)!.replace("]", ""));
  const second = runTool("read", { path: "wide.txt", offset }, w);
  assert.ok(first.length <= MAX_OUT + 100);
  assert.equal(splitLines(first).at(-2), `${offset - 1}\t${row(offset - 1)}`);
  assert.equal(splitLines(second)[0], `${offset}\t${row(offset)}`);
});

test("read limit is clamped to 2000 lines and a past-end offset is an error", () => {
  const w = workdir();
  put(w, "big.txt", "x\n".repeat(5000));
  const out = runTool("read", { path: "big.txt", limit: 4000 }, w);
  const past = runTool("read", { path: "big.txt", offset: 9000 }, w);
  assert.ok(splitLines(out).at(-1)!.endsWith("continue with offset=2001]"));
  assert.equal(past, "error: offset 9000 is past the end of big.txt (5000 lines)");
});

test("a line longer than the cap is marked as cut", () => {
  const w = workdir();
  put(w, "one.txt", "k".repeat(30000) + "TAIL\n");
  const out = runTool("read", { path: "one.txt" }, w);
  assert.ok(out.includes("[line cut: 30004 chars") && !out.includes("TAIL"));
});

test("paths outside the work folder are refused", () => {
  const w = workdir();
  assert.throws(() => runTool("read", { path: "/etc/hostname" }, w), /outside the work folder/);
  assert.throws(() => runTool("write", { path: "../escape.txt", content: "x" }, w), /outside the work folder/);
});

// --- bash -------------------------------------------------------------------------------------

test("short command output is returned whole", () => {
  assert.equal(runTool("bash", { command: "echo hi" }, workdir()), "exit 0\nhi\n");
});

test("long output keeps its first 50 lines, a cut note and its end", () => {
  const out = runTool("bash", { command: "seq 1 10000" }, workdir());
  const rows = splitLines(out);
  assert.deepEqual(rows.slice(0, 3), ["exit 0", "1", "2"]);
  assert.equal(rows[49], "49");
  assert.ok(rows[50].startsWith("...[cut ") && rows.at(-1) === "10000");
  assert.ok(out.length <= MAX_OUT);
});

test("wide first lines keep whole lines within a quarter and the cut count is right", () => {
  const out = runTool("bash", { command: "for i in $(seq 1 1000); do printf 'L%d %0200d\\n' $i 0; done" }, workdir());
  const rows = splitLines(out);
  const at = rows.findIndex((r) => r.startsWith("...[cut "));
  const head = rows.slice(0, at), tail = rows.slice(at + 1);
  assert.ok(head.join("\n").length <= MAX_OUT / 4);
  assert.ok(head.every((r) => r === "exit 0" || r.endsWith("0".repeat(200))));
  assert.equal(rows[at], `...[cut ${1000 + 1 - head.length - tail.length} lines]...`);
  assert.ok(tail.at(-1)!.startsWith("L1000 ") && out.length <= MAX_OUT);
});

test("a few wide lines still keep the summary line at the end", () => {
  const out = runTool("bash", { command: "for i in $(seq 1 9); do printf '%03000d\\n' 0; done; echo 'FAILED 3 passed'" }, workdir());
  assert.equal(splitLines(out).at(-1), "FAILED 3 passed");
  assert.ok(out.length <= MAX_OUT);
});

test("a single huge line keeps its start and its end", () => {
  const out = runTool("bash", { command: "node -e 'console.log(\"S\" + \"z\".repeat(100000) + \"END\")'" }, workdir());
  const rows = splitLines(out);
  assert.ok(rows[0] === "exit 0" && rows[1].startsWith("Szzz") && out.includes("[cut"));
  assert.ok(rows.at(-1)!.endsWith("zEND") && out.length <= MAX_OUT);
});

// --- prompt -----------------------------------------------------------------------------------

test("the system prompt lists the four tools", () => {
  for (const name of ["bash", "read", "edit", "write"]) assert.ok(system("/work").includes(`- ${name}:`));
});
