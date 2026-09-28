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
  const s = { apiKey: "dummy", baseURL: "http://127.0.0.1:9/v1", model: "m", work, log: join(work, "t.jsonl") };
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

test("the real client is made with 6 retries", () => {
  const c = makeClient({ apiKey: "k", baseURL: "http://127.0.0.1:9/v1", model: "m", work: "/", log: "/dev/null" });
  assert.equal((c as unknown as OpenAI).maxRetries, 6);
});

test("a model call error is logged as the stop cause", async () => {
  const { s, client, log } = setup([new OpenAI.APIConnectionError({ message: "Connection error." })]);
  assert.equal(await main("do the task", s, client), 1);
  assert.ok(log().at(-1).stopped.startsWith("api error: "));
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
