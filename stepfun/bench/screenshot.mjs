/**
 * 抓一张真实运行的截图作为验收证据。
 *
 *   node bench/screenshot.mjs [--url http://127.0.0.1:8080] [--out docs/screenshot.png]
 *
 * 流程：加载模型 -> 导入语料 -> 检索 -> 截图（含后端横幅、状态栏、结果列表）。
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const stepfun = path.resolve(here, "..");

const arg = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.split("=")[1] : fallback;
};

const BASE_URL = arg("url", "http://127.0.0.1:8080");
const OUT = path.resolve(stepfun, arg("out", "docs/screenshot.png"));

function pickChannel() {
  const candidates = [
    ["msedge", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"],
    ["msedge", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"],
    ["chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"],
    ["chrome", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"],
  ];
  for (const [channel, exe] of candidates) if (fs.existsSync(exe)) return { channel, exe };
  return null;
}

const picked = pickChannel();
if (!picked) {
  console.error("没找到系统浏览器");
  process.exit(2);
}

const browser = await chromium.launch({
  channel: picked.channel,
  headless: true,
  args: ["--enable-unsafe-webgpu"], // 不要加 --use-angle=swiftshader，否则 WebGPU 拿不到适配器
});
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 1 });
page.on("pageerror", (error) => console.log("  [pageerror]", error.message.slice(0, 200)));

console.log(`打开 ${BASE_URL} ...`);
await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });

const corpus = await page.evaluate(async () => {
  const response = await fetch("./bench/corpus.json");
  return response.json();
});

console.log("加载模型（fp32）...");
const load = await page.evaluate(async () => await window.__kb.loadModel("fp32", false));
console.log(`  后端 ${load.backend} · ${load.loadMs.toFixed(0)} ms`);

console.log("导入语料...");
await page.evaluate(async () => {
  await window.__kb.reset();
});
const imported = await page.evaluate(
  async (docs) => await window.__kb.importDocs(docs),
  corpus.docs.slice(0, 24).map((doc) => ({ id: doc.id, text: doc.text })),
);
console.log(`  ${imported.inserted} 段 · 向量化 ${imported.embedMs.toFixed(0)} ms`);

console.log("检索...");
const query = "睡袋受潮以后还能保暖吗";
const result = await page.evaluate(async (text) => await window.__kb.search(text, 5), query);
console.log(`  命中 ${result.ids.length} 条：${result.ids.join(", ")}`);

// 用界面自身的按钮/输入框再跑一遍，这样截图上是真实的 UI 状态
await page.fill("#corpus", corpus.docs.slice(0, 24).map((doc) => doc.text).join("\n"));
await page.fill("#query", query);
await page.click("#btn-search");
await page.waitForTimeout(2500);

await page.evaluate(() => {
  document.querySelector("#evidence")?.setAttribute("hidden", "hidden");
});

fs.mkdirSync(path.dirname(OUT), { recursive: true });
await page.screenshot({ path: OUT, fullPage: true });
console.log(`截图已保存：${OUT}`);

await browser.close();
