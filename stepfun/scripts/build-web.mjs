/**
 * 构建前端。
 *
 *   node scripts/build-web.mjs
 *
 * 做三件事：
 *   1. 把 onnxruntime-web 的 wasm 文件复制到 web/public/ort/
 *      —— 这样推理不需要联网取 CDN 的 wasm，离线也能跑
 *   2. 把评测语料复制到 web/public/bench/corpus.json
 *   3. 跑 vite build
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { runPnpm } from "./pnpm-runner.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const web = path.join(root, "web");
const publicDir = path.join(web, "public");

function copyDirIfExists(from, to, filter) {
  if (!fs.existsSync(from)) return 0;
  fs.mkdirSync(to, { recursive: true });
  let count = 0;
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, entry.name);
    const dst = path.join(to, entry.name);
    if (entry.isDirectory()) {
      count += copyDirIfExists(src, dst, filter);
    } else if (!filter || filter(entry.name)) {
      fs.copyFileSync(src, dst);
      count += 1;
    }
  }
  return count;
}

// --- 1. onnxruntime-web 的 wasm ---
const ortDist = path.join(web, "node_modules", "onnxruntime-web", "dist");
const ortTarget = path.join(publicDir, "ort");
if (fs.existsSync(ortDist)) {
  const n = copyDirIfExists(
    ortDist,
    ortTarget,
    (name) => name.endsWith(".wasm") || name.endsWith(".mjs"),
  );
  console.log(`[build] onnxruntime-web 运行时已复制 ${n} 个文件到 web/public/ort/`);
  const wasmFiles = fs.readdirSync(ortTarget).filter((f) => f.endsWith(".wasm"));
  for (const file of wasmFiles) {
    const size = fs.statSync(path.join(ortTarget, file)).size;
    console.log(`         ${file}  ${(size / 1024 / 1024).toFixed(1)} MB`);
  }
} else {
  console.warn("[build] 找不到 onnxruntime-web/dist —— 先跑 node scripts/setup.mjs");
}

// --- 2. 评测语料 ---
const corpusSrc = path.join(root, "bench", "corpus", "corpus.json");
if (fs.existsSync(corpusSrc)) {
  fs.mkdirSync(path.join(publicDir, "bench"), { recursive: true });
  fs.copyFileSync(corpusSrc, path.join(publicDir, "bench", "corpus.json"));
  console.log("[build] 评测语料已复制到 web/public/bench/corpus.json");
} else {
  console.warn("[build] 没有语料文件，先跑 node bench/corpus/generate.mjs");
}

// --- 3. vite build ---
console.log("\n[build] vite build ...");
runPnpm(["run", "build"], { cwd: web });
console.log("[build] 完成 -> web/dist");
