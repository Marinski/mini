// Bundle src/cli.ts and its dependencies into one file, dist/mini.js: the sandbox mounts just
// that file into the container, so it must not need node_modules.
import { readFileSync } from "node:fs";
import { build } from "esbuild";

const { version } = JSON.parse(readFileSync("package.json", "utf8"));
await build({
  entryPoints: ["src/cli.ts"], outfile: "dist/mini.js", bundle: true, platform: "node", format: "esm",
  target: "node20", banner: { js: "#!/usr/bin/env node\nimport { createRequire as __cr } from 'node:module'; const require = __cr(import.meta.url);" },
  define: { MINI_VERSION: JSON.stringify(version) }, legalComments: "none",
});
