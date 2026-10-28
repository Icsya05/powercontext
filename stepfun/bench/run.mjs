/**
 * 浏览器端基准：真的在浏览器里跑推理，导出原始数据。
 *
 *   cd bench && corepack pnpm install --ignore-scripts
 *   node run.mjs [--url http://127.0.0.1:8080] [--headed] [--wasm]
 *
 * 用系统已安装的浏览器（Edge/Chrome）驱动，不额外下载 Chromium：
 *   playwright 的 channel:'msedge' 会直接用系统 Edge。
 *
 * 产出 bench/raw/bench-raw-<timestamp>.json，然后交给 score.mjs 算 Recall@K / nDCG@K。
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const RAW_DIR = path.join(here, "raw");

const arg = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.split("=")[1] : fallback;
};
const hasFlag = (name) => process.argv.includes(`--${name}`);

const BASE_URL = arg("url", "http://127.0.0.1:8080");
const HEADED = hasFlag("headed");
const FORCE_WASM = hasFlag("wasm");
const DTYPES = arg("dtypes", "fp32,fp16,q8").split(",").filter(Boolean);
const REPEATS = Number(arg("repeats", "1"));

function pickChannel() {
  const fsMod = fs;
  const candidates = [
    ["msedge", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"],
    ["msedge", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"],
    ["chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"],
    ["chrome", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"],
  ];
  for (const [channel, exe] of candidates) {
    if (fsMod.existsSync(exe)) return { channel, exe };
  }
  return null;
}

const picked = pickChannel();
if (!picked) {
  console.error("没有找到系统浏览器（Edge / Chrome）。请先安装其中一个。");
  process.exit(2);
}
console.log(`浏览器：${picked.channel}  ${picked.exe}`);

const launchOptions = {
  headless: !HEADED,
  args: [
    // 只保留这一条：某些环境需要显式打开 WebGPU。
    // 千万不要加 --use-angle=swiftshader：那会把真实的 GPU 换成软件渲染，
    // 导致 navigator.gpu.requestAdapter() 返回 null，WebGPU 路径根本走不到。
    "--enable-unsafe-webgpu",
  ],
};
if (picked.channel) launchOptions.channel = picked.channel;

const browser = await chromium.launch(launchOptions);
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
});
page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message.slice(0, 300)}`));

const requests = [];
page.on("request", (request) => {
  requests.push({ url: request.url(), method: request.method(), type: request.resourceType() });
});

console.log(`打开 ${BASE_URL} ...`);
await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });

// 语料从页面同源的 /bench/corpus.json 取
const corpus = await page.evaluate(async () => {
  const response = await fetch("./bench/corpus.json");
  if (!response.ok) throw new Error(`语料读取失败 HTTP ${response.status}`);
  return response.json();
});
console.log(`语料：${corpus.docs.length} 篇文档，${corpus.queries.length} 条查询`);

// 记录：整个过程有没有访问过外部推理 API
const externalRequests = requests.filter((r) => {
  const url = r.url;
  return (
    !url.startsWith(BASE_URL) &&
    !url.startsWith("http://127.0.0.1:8080") &&
    !url.startsWith("http://localhost") &&
    !url.startsWith("data:") &&
    !url.startsWith("blob:")
  );
});

const runs = [];

for (const dtype of DTYPES) {
  console.log(`\n=== ${dtype} (${FORCE_WASM ? "强制 WASM" : "优先 WebGPU"}) ===`);

  const loadReport = await page.evaluate(
    async ({ dtype, forceWasm }) => {
      const report = await window.__kb.loadModel(dtype, forceWasm);
      return report;
    },
    { dtype, forceWasm: FORCE_WASM },
  );
  console.log(
    `  模型加载 ${loadReport.loadMs.toFixed(0)} ms · 后端 ${loadReport.backend} · ${loadReport.note}`,
  );

  await page.evaluate(async () => {
    await window.__kb.reset();
  });

  const importReport = await page.evaluate(async (docs) => {
    const report = await window.__kb.importDocs(docs);
    return report;
  }, corpus.docs.map((doc) => ({ id: doc.id, text: doc.text })));
  console.log(
    `  向量化 ${importReport.embedMs.toFixed(0)} ms · 写入 ${importReport.writeMs.toFixed(0)} ms · 索引刷新 ${importReport.refreshMs.toFixed(0)} ms · 库内 ${importReport.total} 段`,
  );

  const results = [];
  for (const query of corpus.queries) {
    const runsOfQuery = [];
    for (let i = 0; i < REPEATS; i += 1) {
      runsOfQuery.push(
        await page.evaluate(async (text) => {
          const result = await window.__kb.search(text);
          return {
            ids: result.ids,
            distances: result.distances,
            searchMs: result.searchMs,
            queryEmbedMs: result.queryEmbedMs,
            usedQueryLeg: result.usedQueryLeg,
            usedRrf: result.usedRrf,
          };
        }, query.text),
      );
    }
    const last = runsOfQuery[runsOfQuery.length - 1];
    const searchTimes = runsOfQuery.map((r) => r.searchMs);
    results.push({
      id: query.id,
      text: query.text,
      keyword: query.text,
      ids: last.ids,
      distances: last.distances,
      searchMs: last.searchMs,
      queryEmbedMs: last.queryEmbedMs,
      searchMsAll: searchTimes,
      usedQueryLeg: last.usedQueryLeg,
      usedRrf: last.usedRrf,
    });
  }
  console.log(`  ${results.length} 条查询完成`);

  runs.push({
    dtype,
    backend: loadReport.backend,
    loadMs: loadReport.loadMs,
    docEmbedMs: importReport.embedMs,
    writeMs: importReport.writeMs,
    refreshMs: importReport.refreshMs,
    results,
  });
}

// 记录外部请求（证明没有调用云端推理）
const externalAfter = requests.filter((r) => {
  const url = r.url;
  return (
    !url.startsWith(BASE_URL) &&
    !url.startsWith("http://127.0.0.1:8080") &&
    !url.startsWith("http://localhost") &&
    !url.startsWith("data:") &&
    !url.startsWith("blob:")
  );
});

const modelName = await page.evaluate(() => window.__kb.modelName());

const payload = {
  generatedAt: new Date().toISOString(),
  model: modelName ?? "unknown",
  corpusSize: corpus.docs.length,
  queryCount: corpus.queries.length,
  forceWasm: FORCE_WASM,
  browser: { channel: picked.channel, exe: picked.exe, headed: HEADED },
  externalRequests: externalAfter.map((r) => r.url),
  runs,
  relevant: Object.fromEntries(corpus.queries.map((q) => [q.id, q.relevant])),
  consoleErrors,
};

fs.mkdirSync(RAW_DIR, { recursive: true });
const stamp = payload.generatedAt.replace(/[:.]/g, "-");
const outPath = path.join(RAW_DIR, `bench-raw-${stamp}.json`);
fs.writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

console.log(`\n原始数据：${outPath}`);
console.log(`外部请求数：${externalAfter.length}${externalAfter.length ? `（${externalAfter.slice(0, 5).join(", ")}）` : " ✅ 没有任何外部请求"}`);
if (consoleErrors.length) {
  console.log(`控制台错误 ${consoleErrors.length} 条：`);
  for (const error of consoleErrors.slice(0, 8)) console.log(`  - ${error}`);
}

await browser.close();
console.log("\n下一步：node bench/score.mjs " + path.relative(path.join(here, ".."), outPath));
