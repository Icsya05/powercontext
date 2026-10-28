/**
 * 安装依赖。
 *
 *   node scripts/setup.mjs
 *
 * 必须用 pnpm：seekdb@1.4.0 的发布包里有 `workspace:` 协议没被重写，
 * npm 装的时候会报 EUNSUPPORTEDPROTOCOL: Unsupported URL Type "workspace:"。
 * 另外 pnpm 12 默认会拦截依赖的构建脚本，这里用 --ignore-scripts 跳过
 * （浏览器端不需要 onnxruntime-node 的原生构建）。
 */

import path from "node:path";
import { fileURLToPath } from "node:url";

import { runPnpm } from "./pnpm-runner.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

const targets = [path.join(root, "server"), path.join(root, "web")];

for (const dir of targets) {
  console.log(`\n=== 安装 ${path.relative(root, dir)} 的依赖 ===`);
  runPnpm(["install", "--ignore-scripts"], { cwd: dir });
}

console.log("\n依赖安装完成。下一步：node scripts/build-web.mjs");
