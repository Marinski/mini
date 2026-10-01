// The loop with a fake client: stop on a plain reply, log prompt size, log an API error as the
// stop cause, and send tool results back to the model.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import OpenAI from "openai";
import { type ChatClient, main, makeClient } from "../src/agent.ts";

function setup(replies: unknown[]) {
  const work = realpathSync(mkdtempSync(join(tmpdir(), "mini-")));
  const s = { apiKey: "dummy", baseURL: "http://127.0.0.1:9/v1", model: "m", work, log: join(mkdtempSync(join(tmpdir(), "mini-log-")), "t.jsonl") };
  const calls: Record<string, unknown>[] = [];
  const client = { chat: { completions: { create: async (body: Record<string, unknown>) => {
    calls.push(structuredClone(body));
    const r = replies.shift();
    if (r instanceof Error) throw r;
    return r;
  } } } } as unknown as ChatClient;
  const log = () => readFileSync(s.log, "utf8").trim().split("\n").map((l) => JSON.parse(l));
  return { s, client, calls, log };
}

const reply = (content: string | null, tool_calls: unknown[] | null = null, prompt_tokens = 123) =>
  ({ choices: [{ message: { content, tool_calls } }], usage: { prompt_tokens } });

test("a plain reply ends the run and logs prompt tokens", async () => {
  const { s, client, calls, log } = setup([reply("done", null, 4321)]);
  assert.equal(await main("do the task", s, client), 0);
  assert.equal(log()[0].prompt_tokens, 4321);
  assert.deepEqual(log()[0].calls, []);
  assert.equal(calls[0].temperature, 0.7);
  assert.equal(calls[0].max_tokens, 8000);
});

test("the real client leaves retries to the loop", () => {
  const c = makeClient({ apiKey: "k", baseURL: "http://127.0.0.1:9/v1", model: "m", work: "/", log: "/dev/null" });
  assert.equal((c as unknown as OpenAI).maxRetries, 0);
});

const connErr = () => new OpenAI.APIConnectionError({ message: "Connection error." });
const noSleep = async () => {};

test("a model call error past the retry window is logged as the stop cause", async () => {
  const { s, client, log } = setup([connErr()]);
  assert.equal(await main("do the task", { ...s, retrySeconds: 0 }, client), 1);
  assert.ok(log().at(-1).stopped.startsWith("api error: "));
});

test("connection errors and 5xx are retried until the model answers", async () => {
  const { s, client, log } = setup([connErr(), new OpenAI.InternalServerError(502, undefined, "Bad Gateway", new Headers()), reply("done")]);
  assert.equal(await main("task", { ...s, sleep: noSleep }, client), 0);
  assert.deepEqual(log().filter((e) => e.retry).map((e) => e.retry), [1, 2]);
  assert.equal(log().at(-1).content, "done");
});

test("a 400 is not retried", async () => {
  const { s, client, log } = setup([new OpenAI.BadRequestError(400, undefined, "bad request", new Headers()), reply("done")]);
  assert.equal(await main("task", { ...s, sleep: noSleep }, client), 1);
  assert.equal(log().filter((e) => e.retry).length, 0);
});

// --- loop breaker -----------------------------------------------------------------------------

const call = (id: string, name: string, args: object) => ({ id, function: { name, arguments: JSON.stringify(args) } });
const bash = (i: number, command = "true") => reply(null, [call(`b${i}`, "bash", { command })]);
const nudges = (log: { nudge?: string }[]) => log.filter((e) => e.nudge).map((e) => e.nudge!);

test("8 tool calls without a file change after the first edit bring a nudge, 16 a stronger one", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 16 }, (_, i) => bash(i)), reply("done")];
  const { s, client, calls, log } = setup(replies);
  assert.equal(await main("task", s, client), 0);
  const n = nudges(log());
  assert.equal(n.length, 2);
  assert.match(n[0], /last 8 tool calls changed no files/);
  assert.match(n[1], /16 tool calls without changing any file. Finish now/);
  // The nudge reaches the model as a user message right after the 8th idle tool result.
  const sent = calls[9].messages as { role: string; content: string }[];
  assert.equal(sent.at(-1)!.role, "user");
  assert.match(sent.at(-1)!.content, /^\[harness\]/);
});

test("exploring before the first change never brings a nudge", async () => {
  const { s, client, log } = setup([...Array.from({ length: 12 }, (_, i) => bash(i)), reply("done")]);
  assert.equal(await main("task", s, client), 0);
  assert.deepEqual(nudges(log()), []);
});

test("a file changed through bash counts as progress", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 6 }, (_, i) => bash(i)), bash(99, "echo y > b.txt"),
    ...Array.from({ length: 6 }, (_, i) => bash(100 + i)), reply("done")];
  const { s, client, log } = setup(replies);
  assert.equal(await main("task", s, client), 0);
  assert.deepEqual(nudges(log()), []);
});

test("MINI_NUDGE_AFTER=0 turns the nudge off", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 10 }, (_, i) => bash(i)), reply("done")];
  const { s, client, log } = setup(replies);
  assert.equal(await main("task", { ...s, nudgeAfter: 0 }, client), 0);
  assert.deepEqual(nudges(log()), []);
});

test("strike mode nudges on the same call repeated, not on idle calls", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 6 }, () => bash(1, "pytest -q")), reply("done")];
  const { s, client, log } = setup(replies);
  assert.equal(await main("task", { ...s, nudgeMode: "strike" }, client), 0);
  const n = nudges(log());
  assert.equal(n.length, 2);
  assert.match(n[0], /run the same tool call 3 times in a row/);
  assert.match(n[1], /same tool call has now run 6 times/);
});

test("strike mode stays silent when the calls differ", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 12 }, (_, i) => bash(i, `echo ${i}`)), reply("done")];
  const { s, client, log } = setup(replies);
  assert.equal(await main("task", { ...s, nudgeMode: "strike" }, client), 0);
  assert.deepEqual(nudges(log()), []);
});

test("strike mode respects MINI_NUDGE_AFTER=0", async () => {
  const replies = [reply(null, [call("w", "write", { path: "a.txt", content: "x" })]),
    ...Array.from({ length: 8 }, () => bash(1, "pytest -q")), reply("done")];
  const { s, client, log } = setup(replies);
  assert.equal(await main("task", { ...s, nudgeMode: "strike", nudgeAfter: 0 }, client), 0);
  assert.deepEqual(nudges(log()), []);
});

test("tool results go back to the model, and tool errors don't stop the run", async () => {
  const call = (id: string, name: string, args: object) => ({ id, function: { name, arguments: JSON.stringify(args) } });
  const { s, client, calls, log } = setup([
    reply(null, [call("1", "write", { path: "a.txt", content: "hi\n" }), call("2", "read", { path: "/etc/passwd" })]),
    reply("done"),
  ]);
  assert.equal(await main("task", s, client), 0);
  const tools = (calls[1].messages as { role: string; content: string }[]).filter((m) => m.role === "tool");
  assert.equal(tools[0].content, "ok");
  assert.match(tools[1].content, /^error: .*outside the work folder/);
  assert.equal(readFileSync(join(s.work, "a.txt"), "utf8"), "hi\n");
  assert.deepEqual(log().filter((e) => e.tool).map((e) => e.tool), ["write", "read"]);
});
