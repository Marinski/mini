// The agent loop: ask the model, run the tool calls it makes, repeat until it replies without
// one, the step limit or the time budget. Transcript format as mini_harness_v2.py, plus
// "retry" and "nudge" entries.
import { appendFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";
import OpenAI from "openai";
import { type NudgeMode, Progress } from "./progress.ts";
import { BUDGET_S, MAX_STEPS, TOOLS, runTool, system } from "./tools.ts";

export interface Settings {
  apiKey: string;
  baseURL: string;
  model: string;
  work: string;
  log: string;
  nudgeAfter?: number; // tool calls without a file change before a nudge; 0 = off (default 8)
  nudgeMode?: NudgeMode; // "after" counts idle tool calls; "strike" counts identical repeats (default "after")
  nudgeStrike?: number; // identical calls in a row before a nudge in "strike" mode (default 3)
  retrySeconds?: number; // how long to keep retrying a failed model call (default 180)
  sleep?: (ms: number) => Promise<unknown>; // for tests
}

// The part of the OpenAI client the loop uses, so tests can pass a fake.
export interface ChatClient {
  chat: { completions: { create(body: Record<string, unknown>): Promise<Completion> } };
}
interface ToolCall { id: string; function: { name: string; arguments: string } }
interface Completion {
  choices: { message: { content: string | null; tool_calls?: ToolCall[] | null } }[];
  usage?: { prompt_tokens?: number } | null;
}

// Retries are ours (below), so the SDK doesn't add its own.
export const makeClient = (s: Settings): ChatClient =>
  new OpenAI({ baseURL: s.baseURL, apiKey: s.apiKey, timeout: 1_800_000, maxRetries: 0 }) as unknown as ChatClient;

// Worth retrying: no connection, a timeout, or the gateway/model being briefly unavailable.
function retryable(e: unknown): boolean {
  if (e instanceof OpenAI.APIConnectionError) return true; // includes timeouts
  const status = e instanceof OpenAI.APIError ? e.status : undefined;
  return status === 408 || status === 409 || status === 429 || (status !== undefined && status >= 500);
}

export async function main(task: string, s: Settings, client: ChatClient = makeClient(s)): Promise<number> {
  const messages: Record<string, unknown>[] = [
    { role: "system", content: system(s.work) },
    { role: "user", content: task },
  ];
  return loop(client, messages, s);
}

export async function loop(client: ChatClient, messages: Record<string, unknown>[], s: Settings): Promise<number> {
  const t0 = Date.now();
  const progress = new Progress(s.work, s.nudgeAfter ?? 8, s.nudgeMode ?? "after", s.nudgeStrike ?? 3);
  const elapsed = () => Math.round((Date.now() - t0) / 100) / 10;
  const log = (entry: object) => appendFileSync(s.log, JSON.stringify(entry) + "\n");
  for (let step = 0; step < MAX_STEPS; step++) {
    if (elapsed() > BUDGET_S) {
      console.log("stopped: time budget");
      return 0;
    }
    let resp: Completion | undefined;
    const retryUntil = Date.now() + (s.retrySeconds ?? 180) * 1000;
    for (let attempt = 1; !resp; attempt++) {
      try {
        resp = await client.chat.completions.create({ model: s.model, messages, tools: TOOLS, temperature: 0.7, max_tokens: 8000 });
      } catch (e) {
        if (!(e instanceof OpenAI.APIError)) throw e;
        const cause = `api error: ${e.constructor.name}: ${e.message}`.slice(0, 500);
        // Back off 1, 2, 4 ... 30 s (with jitter) while the retry window lasts.
        const wait = Math.min(2 ** (attempt - 1), 30) * 1000 * (0.75 + Math.random() / 2);
        if (!retryable(e) || Date.now() + wait > retryUntil) {
          log({ step, t: elapsed(), stopped: cause });
          console.log(`stopped: ${cause}`);
          return 1;
        }
        log({ step, t: elapsed(), retry: attempt, error: cause.slice(0, 200) });
        await (s.sleep ?? sleep)(wait);
      }
    }
    const msg = resp.choices[0].message;
    const calls = msg.tool_calls ?? [];
    const turn: Record<string, unknown> = { role: "assistant", content: msg.content ?? "" };
    if (calls.length) {
      turn.tool_calls = calls.map((c) => ({ id: c.id, type: "function",
        function: { name: c.function.name, arguments: c.function.arguments } }));
    }
    messages.push(turn);
    log({ step, t: elapsed(), content: (msg.content ?? "").slice(0, 2000), calls: calls.map((c) => c.function.name),
      prompt_tokens: resp.usage?.prompt_tokens ?? null });
    if (!calls.length) {
      console.log(msg.content ?? "");
      return 0;
    }
    let nudge: string | null = null;
    for (const call of calls) {
      let result: string;
      try {
        result = runTool(call.function.name, JSON.parse(call.function.arguments || "{}"), s.work);
      } catch (e) { // any tool failure goes back to the model
        result = `error: ${e instanceof Error ? e.message : String(e)}`;
      }
      messages.push({ role: "tool", tool_call_id: call.id, content: result });
      log({ step, tool: call.function.name, result: result.slice(0, 2000) });
      nudge = progress.afterTool(`${call.function.name}\0${call.function.arguments}`) ?? nudge;
    }
    if (nudge) {
      messages.push({ role: "user", content: nudge });
      log({ step, nudge });
    }
  }
  console.log("stopped: step limit");
  return 0;
}
