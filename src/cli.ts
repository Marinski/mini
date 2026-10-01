// mini: command line. By default it re-runs itself in a throwaway Docker container that mounts
// only the current folder, because the agent runs whatever shell commands the model asks for.
import { spawnSync } from "node:child_process";
import { mkdirSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { main } from "./agent.ts";
import type { NudgeMode } from "./progress.ts";

declare const MINI_VERSION: string; // set by the build

const HELP = `mini: a minimal coding agent (bash, read, edit, write) for OpenAI-compatible models.

Usage: mini [options] "task"

  -m, --model <name>     model (env MINI_MODEL or MODEL; default vllm-qwen3.8-nothink)
  -b, --base-url <url>   OpenAI-compatible endpoint (env MINI_BASE_URL or BASE_URL;
                         default http://172.17.0.1:4000/v1)
      --image <image>    sandbox image (env MINI_IMAGE; default node:24-bookworm). It needs node,
                         plus whatever the task's tests need.
      --log <file>       transcript file with --no-sandbox (JSON lines). Default, and always
                         in the sandbox: ~/.local/state/mini/<time>.jsonl
      --no-sandbox       run here, not in a container. Only inside a container you set up
                         yourself: the agent can run any command with your permissions.
  -h, --help             this help
  -v, --version          version

The API key comes from MINI_API_KEY (or LITELLM_KEY / OPENAI_API_KEY), never from a flag.
MINI_NUDGE_AFTER: tool calls without a file change before mini tells the model to step back
(default 8, 0 = off). MINI_NUDGE: the trigger, "after" (idle tool calls) or "strike" (the same
call repeated); default "after". MINI_NUDGE_STRIKE: identical calls in a row before a nudge in
"strike" mode (default 3). MINI_RETRY_SECONDS: how long a failed model call is retried (default 180).
The sandbox mounts only the current folder (as /work) and refuses to run in / or your home folder.`;

const env = process.env;
const first = (...vals: (string | undefined)[]) => vals.find((v) => v);

function stateDir(): string {
  return join(first(env.XDG_STATE_HOME) ?? join(homedir(), ".local", "state"), "mini");
}

function sandbox(task: string, o: { model: string; baseURL: string; image: string }): number {
  const here = realpathSync(process.cwd());
  if (here === "/" || here === realpathSync(homedir())) {
    console.error(`mini: refusing to run in ${here}; the agent can change everything in the folder it runs in. cd into a project first.`);
    return 2;
  }
  const logDir = stateDir();
  mkdirSync(logDir, { recursive: true });
  const logName = `${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`;
  // The container reaches the host as host.docker.internal, not localhost.
  const baseURL = o.baseURL.replace(/\/\/(localhost|127\.0\.0\.1)(?=[:/]|$)/, "//host.docker.internal");
  const self = fileURLToPath(import.meta.url);
  const uid = process.getuid?.(), gid = process.getgid?.();
  const args = [
    "run", "--rm", "-i", ...(process.stdin.isTTY && process.stdout.isTTY ? ["-t"] : []), "--init",
    "--security-opt", "no-new-privileges:true", "--add-host", "host.docker.internal:host-gateway",
    ...(uid !== undefined ? ["--user", `${uid}:${gid}`, "-e", "HOME=/tmp"] : []),
    "-v", `${here}:/work`, "-w", "/work", "-v", `${logDir}:/out`, "-v", `${self}:/opt/mini/mini.js:ro`,
    "-e", "MINI_API_KEY", "-e", `MINI_BASE_URL=${baseURL}`, "-e", `MINI_MODEL=${o.model}`,
    "-e", "MINI_WORK=/work", "-e", `MINI_LOG=/out/${logName}`, "-e", "MINI_NUDGE_AFTER", "-e", "MINI_NUDGE",
    "-e", "MINI_NUDGE_STRIKE", "-e", "MINI_RETRY_SECONDS",
    o.image, "node", "/opt/mini/mini.js", "--no-sandbox", task,
  ];
  console.error(`mini: sandbox ${o.image}, folder ${here}, transcript ${join(logDir, logName)}`);
  const r = spawnSync("docker", args, { stdio: "inherit", env: { ...env, MINI_API_KEY: apiKey() } });
  if (r.error) {
    console.error(`mini: could not start docker (${r.error.message}). Install Docker, or run with --no-sandbox inside your own container.`);
    return 2;
  }
  return r.status ?? 1;
}

const apiKey = () => first(env.MINI_API_KEY, env.LITELLM_KEY, env.OPENAI_API_KEY);

async function cli(): Promise<number> {
  const { values: v, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      model: { type: "string", short: "m" }, "base-url": { type: "string", short: "b" },
      image: { type: "string" }, log: { type: "string" }, "no-sandbox": { type: "boolean" },
      help: { type: "boolean", short: "h" }, version: { type: "boolean", short: "v" },
    },
  });
  if (v.help) return (console.log(HELP), 0);
  if (v.version) return (console.log(MINI_VERSION), 0);
  const task = positionals.join(" ").trim();
  if (!task) return (console.error(HELP), 2);
  if (!apiKey()) return (console.error("mini: set MINI_API_KEY (or LITELLM_KEY / OPENAI_API_KEY)."), 2);
  const model = first(v.model, env.MINI_MODEL, env.MODEL) ?? "vllm-qwen3.8-nothink";
  const baseURL = first(v["base-url"], env.MINI_BASE_URL, env.BASE_URL) ?? "http://172.17.0.1:4000/v1";
  if (!v["no-sandbox"]) {
    return sandbox(task, { model, baseURL, image: first(v.image, env.MINI_IMAGE) ?? "node:24-bookworm" });
  }
  const work = realpathSync(first(env.MINI_WORK, env.WORK) ?? process.cwd());
  let log = first(v.log, env.MINI_LOG, env.LOG);
  if (!log) {
    mkdirSync(stateDir(), { recursive: true });
    log = join(stateDir(), `${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`);
  }
  const int = (v: string | undefined) => (v && /^\d+$/.test(v) ? Number(v) : undefined);
  const mode = (v: string | undefined): NudgeMode | undefined => {
    if (v === undefined) return undefined;
    if (v === "after" || v === "strike") return v;
    console.error(`mini: MINI_NUDGE must be "after" or "strike" (got ${JSON.stringify(v)}); using "after".`);
    return undefined;
  };
  return main(task, { apiKey: apiKey()!, baseURL, model, work, log,
    nudgeAfter: int(env.MINI_NUDGE_AFTER), nudgeMode: mode(env.MINI_NUDGE),
    nudgeStrike: int(env.MINI_NUDGE_STRIKE), retrySeconds: int(env.MINI_RETRY_SECONDS) });
}

cli().then((rc) => process.exit(rc), (e) => {
  console.error(e instanceof Error ? e.stack : e);
  process.exit(1);
});
