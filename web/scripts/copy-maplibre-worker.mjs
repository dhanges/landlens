// MapLibre 6 runs its tile parser in a module worker that it loads from a URL next to its own bundle.
// Next.js bundles maplibre-gl.mjs into a chunk, so that relative URL does not exist; copy the worker into
// public/ and point setWorkerUrl at it (lib/map/maplibre.ts). Runs before dev and build.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const pkg = require.resolve("maplibre-gl/package.json");
const src = join(dirname(pkg), "dist", "maplibre-gl-worker.mjs");
mkdirSync("public/maplibre", { recursive: true });
copyFileSync(src, "public/maplibre/maplibre-gl-worker.mjs");
console.log("copied maplibre-gl-worker.mjs to public/maplibre/");
