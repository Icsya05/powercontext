/**
 * 从基准原始数据计算检索质量指标。
 *
 *   node bench/score.mjs bench/raw/bench-raw-xxx.json
 *
 * 输出 bench/results/quality.md 与 quality.json：
 *   - Recall@K
 *   - nDCG@K（graded relevance：2=直接相关，1=部分相关）
 *   - 每种精度（fp32 / fp16 / q8）一组，以及相对基线的变化幅度
 *
 * 官方 §3.2 第 3 条要求「在同一评测集上对比量化前后的质量，注明评测方法」。
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const RESULTS_DIR = path.join(here, "results");

const K = [1, 3, 5, 10];

function dcg(gains) {
  return gains.reduce((sum, gain, index) => sum + gain / Math.log2(index + 2), 0);
}

function recallAtK(retrieved, relevant, k) {
  const positives = Object.values(relevant).filter((grade) => grade > 0);
  if (!positives.length) return null;
  const top = retrieved.slice(0, k);
  const hit = top.filter((id) => (relevant[id] ?? 0) > 0).length;
  return hit / positives.length;
}

function ndcgAtK(retrieved, relevant, k) {
  const ideal = Object.entries(relevant)
    .sort((a, b) => b[1] - a[1])
    .slice(0, k)
    .map(([, grade]) => grade);
  if (!ideal.length) return null;
  const gains = retrieved.slice(0, k).map((id) => relevant[id] ?? 0);
  const idcg = dcg(ideal);
  return idcg === 0 ? 0 : dcg(gains) / idcg;
}

function average(values) {
  const valid = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!valid.length) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function median(values) {
  const valid = values.filter((value) => typeof value === "number" && Number.isFinite(value)).sort((a, b) => a - b);
  if (!valid.length) return null;
  const mid = Math.floor(valid.length / 2);
  return valid.length % 2 ? valid[mid] : (valid[mid - 1] + valid[mid]) / 2;
}

/** 从本地模型清单里读各精度的实际体积（与 fetch-model.mjs 写的口径一致）。 */
function readModelSizes(model) {
  const manifestPath = path.join(
    here,
    "..",
    "web",
    "public",
    "models",
    model,
    "local-manifest.json",
  );
  if (!fs.existsSync(manifestPath)) return {};
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const byDtype = {};
  for (const dtype of manifest.dtypes ?? []) {
    const file = manifest.files?.find((f) => f.file.startsWith("onnx/"));
    // local-manifest 里 files 是按 COMMON + dtype 的顺序排的，这里按 onnx/ 找对应变体
    const onnx = manifest.files?.filter((f) => f.file.startsWith("onnx/")) ?? [];
    const index = (manifest.dtypes ?? []).indexOf(dtype);
    const entry = onnx[index];
    if (entry) byDtype[dtype] = entry.bytes;
  }
  return byDtype;
}

export function score(raw) {
  const runs = [];
  const modelSizes = readModelSizes(raw.model);
  for (const run of raw.runs ?? []) {
    const metrics = {};
    for (const k of K) {
      const recalls = [];
      const ndcgs = [];
      for (const item of run.results ?? []) {
        const relevant = raw.relevant?.[item.id] ?? item.relevant ?? {};
        const recall = recallAtK(item.ids ?? [], relevant, k);
        const ndcg = ndcgAtK(item.ids ?? [], relevant, k);
        if (recall !== null) recalls.push(recall);
        if (ndcg !== null) ndcgs.push(ndcg);
      }
      metrics[`Recall@${k}`] = average(recalls);
      metrics[`nDCG@${k}`] = average(ndcgs);
    }
    const searchTimes = (run.results ?? []).map((item) => item.searchMs);
    const queryEmbedTimes = (run.results ?? []).map((item) => item.queryEmbedMs);
    runs.push({
      dtype: run.dtype,
      backend: run.backend,
      modelBytes: modelSizes[run.dtype] ?? null,
      loadMs: run.loadMs,
      docEmbedMs: run.docEmbedMs,
      writeMs: run.writeMs,
      refreshMs: run.refreshMs,
      queryCount: (run.results ?? []).length,
      searchMsMedian: median(searchTimes),
      queryEmbedMsMedian: median(queryEmbedTimes),
      metrics,
    });
  }
  return {
    generatedAt: new Date().toISOString(),
    model: raw.model,
    corpusSize: raw.corpusSize,
    queryCount: raw.queryCount,
    forceWasm: raw.forceWasm,
    k: K,
    runs,
  };
}

function renderMarkdown(scored) {
  const lines = [];
  lines.push("# 检索质量报告（Recall@K / nDCG@K）");
  lines.push("");
  lines.push(`- 模型：\`${scored.model}\``);
  lines.push(`- 语料：${scored.corpusSize} 篇文档`);
  lines.push(`- 查询集：${scored.queryCount} 条（带 graded relevance：2=直接相关，1=部分相关）`);
  lines.push(`- 强制 WASM：${scored.forceWasm ? "是" : "否"}`);
  lines.push(`- 生成时间：${scored.generatedAt}`);
  lines.push("");
  lines.push("## 评测方法");
  lines.push("");
  lines.push("- **Recall@K** = 检索结果前 K 条中命中的相关文档数 / 全部相关文档数");
  lines.push("- **nDCG@K** = DCG@K / IDCG@K，DCG 用 `gain / log2(rank+1)`，增益取 graded relevance（2 或 1），IDCG 按相关性降序排列取前 K 条");
  lines.push("- 每条查询只统计一次，最终为所有查询的算术平均");
  lines.push("");
  lines.push("## 结果");
  lines.push("");
  const header = ["配置", "模型体积(B)", "压缩比", ...scored.k.flatMap((k) => [`Recall@${k}`, `nDCG@${k}`]), "检索延迟中位数(ms)"];
  lines.push(`| ${header.join(" | ")} |`);
  lines.push(`| ${header.map(() => "---").join(" | ")} |`);
  const baselineBytes = scored.runs.find((r) => r.dtype === "fp32")?.modelBytes;
  for (const run of scored.runs) {
    const ratio =
      baselineBytes && run.modelBytes ? (baselineBytes / run.modelBytes).toFixed(3) : "-";
    const cells = [
      `${run.dtype} + ${run.backend.toUpperCase()}`,
      run.modelBytes ? String(run.modelBytes) : "-",
      ratio === "-" ? "-" : `${ratio}x`,
      ...scored.k.flatMap((k) => [
        run.metrics[`Recall@${k}`]?.toFixed(4) ?? "-",
        run.metrics[`nDCG@${k}`]?.toFixed(4) ?? "-",
      ]),
      run.searchMsMedian?.toFixed(2) ?? "-",
    ];
    lines.push(`| ${cells.join(" | ")} |`);
  }
  lines.push("");

  const baseline = scored.runs[0];
  if (baseline && scored.runs.length > 1) {
    lines.push("## 相对量化前基线的变化");
    lines.push("");
    lines.push(`基线 = \`${baseline.dtype} + ${baseline.backend.toUpperCase()}\``);
    lines.push("");
    lines.push("| 配置 | ΔRecall@5 | ΔnDCG@5 | ΔRecall@10 | ΔnDCG@10 |");
    lines.push("| --- | --- | --- | --- | --- |");
    for (const run of scored.runs.slice(1)) {
      const delta = (metric) => {
        const a = run.metrics[metric];
        const b = baseline.metrics[metric];
        if (a === null || a === undefined || b === null || b === undefined) return "-";
        const diff = a - b;
        return `${diff >= 0 ? "+" : ""}${(diff * 100).toFixed(2)} 个百分点`;
      };
      lines.push(
        `| ${run.dtype} + ${run.backend.toUpperCase()} | ${delta("Recall@5")} | ${delta("nDCG@5")} | ${delta("Recall@10")} | ${delta("nDCG@10")} |`,
      );
    }
    lines.push("");
  }

  lines.push("## 分阶段耗时（每种配置）");
  lines.push("");
  lines.push("| 配置 | 模型加载(ms) | 文档向量化(ms) | 写入(ms) | 索引刷新(ms) | 查询向量化中位数(ms) | seekdb 检索中位数(ms) |");
  lines.push("| --- | --- | --- | --- | --- | --- | --- |");
  for (const run of scored.runs) {
    lines.push(
      `| ${run.dtype} + ${run.backend.toUpperCase()} | ${run.loadMs?.toFixed(0) ?? "-"} | ${run.docEmbedMs?.toFixed(0) ?? "-"} | ${run.writeMs?.toFixed(0) ?? "-"} | ${run.refreshMs?.toFixed(0) ?? "-"} | ${run.queryEmbedMsMedian?.toFixed(2) ?? "-"} | ${run.searchMsMedian?.toFixed(2) ?? "-"} |`,
    );
  }
  lines.push("");
  return lines.join("\n");
}

// ---------------------------------------------------------------- CLI
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  const inputs = process.argv.slice(2).filter((a) => !a.startsWith("--"));
  if (!inputs.length) {
    console.error("用法：node bench/score.mjs <bench-raw-xxx.json> [更多原始数据文件...]");
    process.exit(2);
  }

  // 合并多份原始数据：不同文件通常是不同推理后端（WebGPU / WASM）的跑次，
  // 官方建议的表就是「基线 / 量化+WebGPU / 量化+WASM」三行。
  const merged = { runs: [], corpusSize: 0, queryCount: 0, model: "", forceWasm: false, relevant: {} };
  for (const input of inputs) {
    const raw = JSON.parse(fs.readFileSync(path.resolve(input), "utf8"));

    // 相关性标注来自语料文件（生成器写进 corpus.json），raw 里可能没带
    if (!raw.relevant) {
      const corpusPath = path.join(here, "corpus", "corpus.json");
      if (fs.existsSync(corpusPath)) {
        const corpus = JSON.parse(fs.readFileSync(corpusPath, "utf8"));
        raw.relevant = Object.fromEntries((corpus.queries ?? []).map((q) => [q.id, q.relevant]));
      }
    }

    merged.model = merged.model || raw.model;
    merged.corpusSize = raw.corpusSize ?? merged.corpusSize;
    merged.queryCount = raw.queryCount ?? merged.queryCount;
    merged.forceWasm = merged.forceWasm || Boolean(raw.forceWasm);
    Object.assign(merged.relevant, raw.relevant ?? {});
    merged.runs.push(...(raw.runs ?? []));
  }

  const scored = score(merged);
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.writeFileSync(path.join(RESULTS_DIR, "quality.json"), `${JSON.stringify(scored, null, 2)}\n`, "utf8");
  fs.writeFileSync(path.join(RESULTS_DIR, "quality.md"), renderMarkdown(scored), "utf8");
  console.log(renderMarkdown(scored));
  console.log(`\n已写入 ${path.join(RESULTS_DIR, "quality.md")}`);
}
