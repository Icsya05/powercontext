/**
 * 预置 embedding 模型到 web/public/models/。
 *
 *   node scripts/fetch-model.mjs [--dtypes fp32,fp16,q8]
 *
 * 为什么要有这个脚本：
 *  1. 评审环境可能连不上 huggingface.co，模型必须能离线加载；
 *  2. 量化对比需要同一模型的多个精度变体（fp32 / fp16 / q8），
 *     而浏览器默认只会拉当前 dtype 对应的那一个；
 *  3. 有了本地副本，「模型体积」就能用同一口径精确统计（文件实际字节数）。
 *
 * 浏览器端加载逻辑（web/src/embedder.ts）：
 *   env.allowLocalModels = true + env.localModelPath = '/models/'
 *   -> Transformers.js 优先用本地文件，找不到再回落到官方 CDN。
 *   模型在本地之后，浏览器完全不需要连 huggingface.co —— 这对评审环境最稳。
 *
 * 下载用 curl 而不是 fetch：Node 内置的 undici 不认 HTTPS_PROXY 环境变量，
 * 而本机必须走代理才能出网（DNS 被污染）。
 *
 * 模型文件不进 git（体积大），由 .gitignore 排除；评审跑一次 setup 即可。
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const targetRoot = path.join(root, "web", "public", "models");

const MODEL = process.env.EMBED_MODEL ?? "Xenova/bge-small-zh-v1.5";
const BASE = process.env.HF_BASE ?? "https://huggingface.co";

// dtype -> ONNX 文件名（与 Transformers.js 的 DEFAULT_DTYPE_SUFFIX_MAPPING 一致）
const DTYPE_FILES = {
  fp32: "onnx/model.onnx",
  fp16: "onnx/model_fp16.onnx",
  q8: "onnx/model_quantized.onnx",
  int8: "onnx/model_int8.onnx",
  uint8: "onnx/model_uint8.onnx",
  q4: "onnx/model_q4.onnx",
};

const argDtypes = process.argv.find((a) => a.startsWith("--dtypes="))?.split("=")[1];
const dtypes = (argDtypes ? argDtypes.split(",") : ["fp32", "fp16", "q8"]).filter((d) =>
  DTYPE_FILES[d],
);
if (!dtypes.length) {
  console.error(`--dtypes 至少要有一个合法值，可选：${Object.keys(DTYPE_FILES).join(", ")}`);
  process.exit(2);
}

// 不同模型附带的辅助文件不一样（bge-small-zh 没有 vocab.txt / special_tokens_map.json），
// 所以这些文件下载时 404 视为「这个模型不需要」，跳过即可。
const COMMON_FILES = [
  "config.json",
  "tokenizer.json",
  "tokenizer_config.json",
  "special_tokens_map.json",
  "vocab.txt",
];

const CURL = process.platform === "win32" ? "curl.exe" : "curl";

function download(url, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const result = spawnSync(
    CURL,
    ["-sS", "-L", "--fail", "--max-time", "600", "--retry", "3", "--retry-delay", "2", "-o", dest, url],
    { stdio: ["ignore", "inherit", "inherit"], shell: false },
  );
  if (result.status === 0 && fs.existsSync(dest) && fs.statSync(dest).size > 0) return "ok";
  // 404 = 这个模型没有这个文件，跳过；其它错误算失败。
  if (result.status === 22) return "missing";
  return "failed";
}

const modelDir = path.join(targetRoot, MODEL);
fs.mkdirSync(modelDir, { recursive: true });

const files = [...COMMON_FILES, ...dtypes.map((dtype) => DTYPE_FILES[dtype])];

console.log(`模型：${MODEL}`);
console.log(`目标：${modelDir}`);
console.log(`文件：${files.length} 个`);
console.log(
  `代理：${process.env.HTTPS_PROXY ?? process.env.HTTP_PROXY ?? "（未设置，直连）"}\n`,
);

const manifest = [];
let total = 0;
let failed = 0;

for (const file of files) {
  const url = `${BASE}/${MODEL}/resolve/main/${file}`;
  const dest = path.join(modelDir, ...file.split("/"));

  if (fs.existsSync(dest) && fs.statSync(dest).size > 0) {
    const size = fs.statSync(dest).size;
    console.log(`  [skip] ${file.padEnd(26)} 已存在 (${(size / 1024 / 1024).toFixed(1)} MB)`);
    manifest.push({ file, bytes: size });
    total += size;
    continue;
  }

  process.stdout.write(`  [get ] ${file.padEnd(26)}`);
  const status = download(url, dest);
  if (status === "missing") {
    console.log(" 该模型没有这个文件，跳过");
    continue;
  }
  if (status !== "ok") {
    console.log(" 失败");
    failed += 1;
    continue;
  }
  const size = fs.statSync(dest).size;
  total += size;
  console.log(` ${(size / 1024 / 1024).toFixed(1)} MB`);
  manifest.push({ file, bytes: size });
}

const manifestPath = path.join(modelDir, "local-manifest.json");
fs.writeFileSync(
  manifestPath,
  `${JSON.stringify({ model: MODEL, dtypes, files: manifest, totalBytes: total }, null, 2)}\n`,
  "utf8",
);

console.log(`\n完成。${manifest.length} 个文件，合计 ${(total / 1024 / 1024).toFixed(1)} MB`);
console.log(`清单：${manifestPath}`);

console.log("\n各精度体积（用于 §3.2 的「对比模型体积」）：");
const fp32Bytes = manifest.find((m) => m.file === DTYPE_FILES.fp32)?.bytes;
for (const dtype of dtypes) {
  const entry = manifest.find((m) => m.file === DTYPE_FILES[dtype]);
  if (!entry) continue;
  const ratio = fp32Bytes ? (fp32Bytes / entry.bytes).toFixed(3) : "-";
  console.log(
    `  ${dtype.padEnd(6)} ${entry.file.padEnd(28)} ${String(entry.bytes).padStart(10)} B   压缩比 ${ratio}x`,
  );
}

if (failed) {
  console.error(`\n有 ${failed} 个文件下载失败 —— 检查代理是否可用（HTTP_PROXY / HTTPS_PROXY）。`);
  process.exit(1);
}
