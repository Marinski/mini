// The agent loop: ask the model, run the tool calls it makes, repeat until it replies without
// one, the step limit or the time budget. Same transcript format as mini_harness_v2.py.
import { appendFileSync } from "node:fs";
import OpenAI from "openai";
import { BUDGET_S, MAX_STEPS, TOOLS, runTool, system } from "./tools.ts";

export interface Settings {
  apiKey: string;
  baseURL: string;
  model: string;
  work: string;
  log: string;
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

export const makeClient = (s: Settings): ChatClient =>
  new OpenAI({ baseURL: s.baseURL, apiKey: s.apiKey, timeout: 1_800_000, maxRetries: 6 }) as unknown as ChatClient;

export async function main(task: string, s: Settings, client: ChatClient = makeClient(s)): Promise<number> {
  const messages: Record<string, unknown>[] = [
    { role: "system", content: system(s.work) },
    { role: "user", content: task },
  ];
  return loop(client, messages, s);
}

export async function loop(client: ChatClient, messages: Record<string, unknown>[], s: Settings): Promise<number> {
  const t0 = Date.now();
  const elapsed = () => Math.round((Date.now() - t0) / 100) / 10;
  const log = (entry: object) => appendFileSync(s.log, JSON.stringify(entry) + "\n");
  for (let step = 0; step < MAX_STEPS; step++) {
    if (elapsed() > BUDGET_S) {
      console.log("stopped: time budget");
      return 0;
    }
    let resp: Completion;
    try {
      resp = await client.chat.completions.create({ model: s.model, messages, tools: TOOLS, temperature: 0.7, max_tokens: 8000 });
    } catch (e) {
      if (!(e instanceof OpenAI.APIError)) throw e;
      const cause = `api error: ${e.constructor.name}: ${e.message}`.slice(0, 500);
      log({ step, t: elapsed(), stopped: cause });
      console.log(`stopped: ${cause}`);
      return 1;
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
    for (const call of calls) {
      let result: string;
      try {
        result = runTool(call.function.name, JSON.parse(call.function.arguments || "{}"), s.work);
      } catch (e) { // any tool failure goes back to the model
        result = `error: ${e instanceof Error ? e.message : String(e)}`;
      }
      messages.push({ role: "tool", tool_call_id: call.id, content: result });
      log({ step, tool: call.function.name, result: result.slice(0, 2000) });
    }
  }
  console.log("stopped: step limit");
  return 0;
}
