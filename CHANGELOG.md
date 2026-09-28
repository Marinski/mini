# Changelog

## 0.3.0

- Loop breaker: after the first file change, 8 tool calls in a row that change no file bring a
  note from the harness (re-read the task and checklist, check whether your own test is wrong,
  stop if done); 16 bring a firmer "finish now". `MINI_NUDGE_AFTER` sets the count (0 = off).
  File changes are detected from the folder, so edits made through bash count.
- Prompt: keep a requirement checklist, and treat your own failing test as suspect too.
- Retries: a failed model call (connection error, timeout, 408/409/429/5xx) is retried with
  backoff for up to 3 minutes (`MINI_RETRY_SECONDS`), enough to ride out a gateway restart.
  Retries and nudges are logged in the transcript.

## 0.2.0

- First npm release: mini in TypeScript, a port of the Python mini v2 (same tools, prompt,
  limits, retries and transcript format).
- Runs in a throwaway Docker container that mounts only the current folder by default
  (refuses `/` and your home folder); `--no-sandbox` runs in place.
- One-file bundle (`dist/mini.js`), no runtime dependencies. Node 20+.
