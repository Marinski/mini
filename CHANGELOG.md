# Changelog

## 0.2.0

- First npm release: mini in TypeScript, a port of the Python mini v2 (same tools, prompt,
  limits, retries and transcript format).
- Runs in a throwaway Docker container that mounts only the current folder by default
  (refuses `/` and your home folder); `--no-sandbox` runs in place.
- One-file bundle (`dist/mini.js`), no runtime dependencies. Node 20+.
