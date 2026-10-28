/**
 * 端侧合规静态自检。
 *
 *   node scripts/check_compliance.mjs
 *
 * 这是官方 §2.5 / §3.1-2 的**机器可验证证据**：
 *   1. server/package.json 的依赖里不能出现任何 embedding / 模型包
 *   2. server/ 的源码里不能 import 任何 embedding / 模型包
 *   3. server/ 的源码里不能出现云端推理 API 的域名
 *   4. web/ 必须依赖浏览器端运行时（@huggingface/transformers）
 *
 * 退出码非 0 表示不合规。
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const serverDir = path.join(root, "server");
const webDir = path.join(root, "web");

/** 服务端绝对不允许出现的包（embedding / 模型 / 云端推理）。 */
const FORBIDDEN_IN_SERVER = [
  "@huggingface/transformers",
  "@xenova/transformers",
  "@huggingface/tokenizers",
  "@huggingface/jinja",
  "onnxruntime-node",
  "onnxruntime-web",
  "@seekdb/default-embed",
  "@seekdb/qwen",
  "@seekdb/openai",
  "@seekdb/jina",
  "@seekdb/bm25",
  "transformers",
  "sentence-transformers",
  "@xenova/all-minilm-l6-v2",
];

/** 服务端绝对不允许出现的云端推理域名。 */
const FORBIDDEN_HOSTS = [
  "api.openai.com",
  "api.minimax.io",
  "dashscope.aliyuncs.com",
  "api.jina.ai",
  "generativelanguage.googleapis.com",
  "api.anthropic.com",
];

function walk(dir, filter = () => true) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === "dist" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, filter));
    else if (filter(entry.name)) out.push(full);
  }
  return out;
}

/**
 * 去掉注释后再检查。
 * 否则「解释某个坑的注释」里出现的包名会被误判成真的依赖
 * （比如 store.mjs 里为了说明 SDK 行为写了 @seekdb/default-embed）。
 */
function stripComments(text) {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const failures = [];
const passes = [];

function check(ok, label, detail) {
  if (ok) {
    passes.push(label);
    console.log(`  [PASS] ${label}${detail ? `  ${detail}` : ""}`);
  } else {
    failures.push(`${label}${detail ? `  ${detail}` : ""}`);
    console.log(`  [FAIL] ${label}${detail ? `  ${detail}` : ""}`);
  }
}

console.log("=== 端侧合规自检 ===\n");

// --- 1. 服务端依赖 ---
console.log("[1] server/package.json 的依赖");
const serverPkg = JSON.parse(fs.readFileSync(path.join(serverDir, "package.json"), "utf8"));
const serverDeps = Object.keys(serverPkg.dependencies ?? {});
console.log(`      依赖列表：${serverDeps.length ? serverDeps.join(", ") : "（空）"}`);
for (const forbidden of FORBIDDEN_IN_SERVER) {
  check(!serverDeps.includes(forbidden), `服务端不依赖 ${forbidden}`);
}
check(serverDeps.length === 1 && serverDeps[0] === "seekdb", "服务端只有 seekdb 一个运行时依赖", `实际：${serverDeps.join(", ")}`);

// --- 2. 服务端源码 ---
console.log("\n[2] server/ 源码里的 import 与云端域名");
const serverFiles = walk(serverDir, (name) => name.endsWith(".mjs") || name.endsWith(".js"));
check(serverFiles.length > 0, "找到服务端源文件", `${serverFiles.length} 个`);
for (const file of serverFiles) {
  const text = stripComments(fs.readFileSync(file, "utf8"));
  const rel = path.relative(root, file);
  for (const forbidden of FORBIDDEN_IN_SERVER) {
    check(!text.includes(forbidden), `${rel} 里没有出现 ${forbidden}`);
  }
  for (const host of FORBIDDEN_HOSTS) {
    check(!text.includes(host), `${rel} 里没有出现云端推理域名 ${host}`);
  }
}

// --- 3. 服务端不做排序 ---
console.log("\n[3] 服务端没有自己实现排序/打分");
const serverText = serverFiles.map((f) => stripComments(fs.readFileSync(f, "utf8"))).join("\n");
check(!/\bfunction\s+(merge|rerank|score|rank)\w*\s*\(/i.test(serverText), "服务端没有自实现 merge/rerank/score/rank 函数");
check(serverText.includes("hybridSearch"), "服务端调用 seekdb 的 hybridSearch");

// --- 4. 浏览器端必须依赖端侧运行时 ---
console.log("\n[4] web/package.json");
const webPkg = JSON.parse(fs.readFileSync(path.join(webDir, "package.json"), "utf8"));
const webDeps = { ...(webPkg.dependencies ?? {}), ...(webPkg.devDependencies ?? {}) };
check(Boolean(webDeps["@huggingface/transformers"]), "web 依赖 @huggingface/transformers");
check(!webDeps["@seekdb/default-embed"] && !webDeps["@seekdb/qwen"], "web 没有依赖云端 embedding 包");
check(!webPkg.dependencies?.["seekdb"], "web 不依赖 seekdb（数据库只在服务端）");

// --- 5. 关键 API 语义 ---
console.log("\n[5] 端侧关键语义");
const storeText = fs.readFileSync(path.join(serverDir, "src", "store.mjs"), "utf8");
check(/embeddingFunction:\s*null/.test(storeText), "Schema 里 embeddingFunction: null（不让 SDK 在服务端算向量）");
check(/refresh_index\(\)/.test(storeText), "写入后调用 refresh_index()（异步索引必须刷新）");
check(/queryEmbeddings:\s*\[queryVector\]/.test(storeText), "查询向量由浏览器传入，原样交给 seekdb");

// --- 汇总 ---
console.log(`\n=== 结果：${passes.length} 项通过，${failures.length} 项失败 ===`);
if (failures.length) {
  for (const failure of failures) console.log(`  ! ${failure}`);
  process.exit(1);
}
console.log("端侧合规自检全部通过 ✅");
