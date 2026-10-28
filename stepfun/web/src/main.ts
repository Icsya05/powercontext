/**
 * 前端主程序。
 *
 * 所有推理都在这个页面里完成（浏览器 = 用户设备）。
 * 服务端只接收已经算好的浮点数组。
 */

import "./style.css";
import { api, type SearchResult } from "./api";
import {
  DTYPE_OPTIONS,
  MODEL_ID,
  chunkText,
  embedTexts,
  embedQuery,
  getLoadReport,
  loadEmbedder,
  probeWebGPU,
  specFor,
  type Dtype,
} from "./embedder";

// ---------------------------------------------------------------- DOM
const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`缺少元素 #${id}`);
  return el as T;
};

const els = {
  backendDot: $<HTMLSpanElement>("backend-dot"),
  backendText: $<HTMLSpanElement>("backend-text"),
  dtype: $<HTMLSelectElement>("dtype"),
  forceWasm: $<HTMLInputElement>("force-wasm"),
  btnLoad: $<HTMLButtonElement>("btn-load"),
  modelStatus: $<HTMLDivElement>("model-status"),
  corpus: $<HTMLTextAreaElement>("corpus"),
  btnImport: $<HTMLButtonElement>("btn-import"),
  btnDemo: $<HTMLButtonElement>("btn-demo"),
  importStatus: $<HTMLSpanElement>("import-status"),
  importBar: $<HTMLDivElement>("import-bar"),
  query: $<HTMLInputElement>("query"),
  btnSearch: $<HTMLButtonElement>("btn-search"),
  searchStatus: $<HTMLSpanElement>("search-status"),
  results: $<HTMLDivElement>("results"),
  btnSchema: $<HTMLButtonElement>("btn-schema"),
  btnRows: $<HTMLButtonElement>("btn-rows"),
  btnReset: $<HTMLButtonElement>("btn-reset"),
  btnBench: $<HTMLButtonElement>("btn-bench"),
  evidence: $<HTMLPreElement>("evidence"),
};

// ---------------------------------------------------------------- 工具
function setStatus(el: HTMLElement, text: string, kind: "" | "ok" | "err" | "warn" = "") {
  el.textContent = text;
  el.className = `status ${kind}`.trim();
}

function showEvidence(title: string, payload: unknown) {
  els.evidence.hidden = false;
  els.evidence.textContent =
    `=== ${title} ===\n` + (typeof payload === "string" ? payload : JSON.stringify(payload, null, 2));
}

let corpusCache: { docs: { id: string; text: string }[]; queries: BenchQuery[] } | null = null;

interface BenchQuery {
  id: string;
  text: string;
  keyword: string;
  relevant: string[];
}

// ---------------------------------------------------------------- 启动
async function init() {
  for (const option of DTYPE_OPTIONS) {
    const opt = document.createElement("option");
    opt.value = option.value;
    opt.textContent = `${option.label} · ${option.note}`;
    els.dtype.appendChild(opt);
  }
  els.dtype.value = "fp32";

  const probe = await probeWebGPU();
  els.backendDot.className = `dot ${probe.adapter ? "ok" : "warn"}`;
  els.backendText.textContent = probe.adapter
    ? `检测到 WebGPU（${probe.reason}）· 加载模型时会优先使用 WebGPU`
    : `未检测到可用的 WebGPU（${probe.reason}）· 将自动降级到 WASM`;

  const spec = specFor(MODEL_ID);
  const modelName = document.getElementById("model-name");
  if (modelName) modelName.textContent = `${MODEL_ID}（${spec.dimension} 维，${spec.pooling} 池化）`;

  try {
    const health = await api.health();
    setStatus(
      els.modelStatus,
      `seekdb ${health.db.connected ? "已连接" : "未连接"} · ${health.db.host}:${health.db.port}/${health.db.database} · 集合 ${health.db.collection} · ${health.db.dimension} 维`,
      health.db.connected ? "ok" : "err",
    );
  } catch (error) {
    setStatus(els.modelStatus, `服务端未就绪：${(error as Error).message}`, "err");
  }

  wire();
}

function wire() {
  els.btnLoad.addEventListener("click", onLoad);
  els.btnImport.addEventListener("click", onImport);
  els.btnDemo.addEventListener("click", onDemo);
  els.btnSearch.addEventListener("click", onSearch);
  els.btnSchema.addEventListener("click", onSchema);
  els.btnRows.addEventListener("click", onRows);
  els.btnReset.addEventListener("click", onReset);
  els.btnBench.addEventListener("click", onBench);
}

// ---------------------------------------------------------------- 1. 模型
async function onLoad() {
  els.btnLoad.disabled = true;
  setStatus(els.modelStatus, "正在加载模型（首次会下载模型文件）…");
  try {
    const report = await loadEmbedder(els.dtype.value as Dtype, {
      forceWasm: els.forceWasm.checked,
    });
    els.backendDot.className = `dot ${report.backend === "webgpu" ? "ok" : "warn"}`;
    els.backendText.textContent = `当前推理后端：${report.backend.toUpperCase()} · ${report.note}`;
    setStatus(
      els.modelStatus,
      `模型已加载 · 后端 ${report.backend} · dtype ${report.dtype} · 加载耗时 ${report.loadMs.toFixed(0)} ms · ${report.model}`,
      "ok",
    );
  } catch (error) {
    setStatus(els.modelStatus, `模型加载失败：${(error as Error).message}`, "err");
  } finally {
    els.btnLoad.disabled = false;
  }
}

// ---------------------------------------------------------------- 2. 导入
async function onImport() {
  const raw = els.corpus.value;
  if (!raw.trim()) {
    setStatus(els.importStatus, "先粘贴一些文本", "warn");
    return;
  }
  const lines = raw
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    setStatus(els.importStatus, "没有可导入的文本", "warn");
    return;
  }

  els.btnImport.disabled = true;
  const stamp = Date.now();
  const ids = lines.map((_, index) => `imp_${stamp}_${index}`);
  const chunks: string[] = [];
  const chunkOwner: string[] = [];
  lines.forEach((line, index) => {
    for (const piece of chunkText(line)) {
      chunks.push(piece);
      chunkOwner.push(ids[index]);
    }
  });

  try {
    setStatus(els.importStatus, `本地切块 ${chunks.length} 段，正在浏览器内向量化…`);
    els.importBar.style.width = "35%";
    const { vectors, embedMs } = await embedTexts(chunks, { batchSize: 16 });
    els.importBar.style.width = "70%";
    setStatus(els.importStatus, `向量化完成（${embedMs.toFixed(0)} ms），写入 seekdb…`);

    const response = await api.addDocuments({
      ids: chunkOwner,
      documents: chunks,
      embeddings: vectors,
      metadatas: chunkOwner.map((id, index) => ({
        id,
        source: "paste",
        chunk: index,
      })),
    });

    els.importBar.style.width = "100%";
    setStatus(
      els.importStatus,
      `入库完成 · 新增 ${response.inserted} 段 · 写入 ${response.writeMs.toFixed(0)} ms · 索引刷新 ${response.refreshMs.toFixed(0)} ms · 库内共 ${response.total} 段`,
      "ok",
    );
  } catch (error) {
    els.importBar.style.width = "0%";
    setStatus(els.importStatus, `导入失败：${(error as Error).message}`, "err");
  } finally {
    els.btnImport.disabled = false;
  }
}

async function onDemo() {
  try {
    const corpus = await loadCorpus();
    els.corpus.value = corpus.docs.slice(0, 12).map((doc) => doc.text).join("\n");
    setStatus(els.importStatus, `已填入 ${Math.min(12, corpus.docs.length)} 段示例语料`, "ok");
  } catch (error) {
    setStatus(els.importStatus, `示例语料读取失败：${(error as Error).message}`, "err");
  }
}

// ---------------------------------------------------------------- 3. 检索
async function onSearch() {
  const text = els.query.value.trim();
  if (!text) {
    setStatus(els.searchStatus, "请输入查询", "warn");
    return;
  }
  els.btnSearch.disabled = true;
  try {
    setStatus(els.searchStatus, "浏览器本地生成查询向量…");
    const { vector, embedMs } = await embedQuery(text);
    setStatus(els.searchStatus, "查询向量已生成，调用 seekdb 混合检索…");
    const result = await api.search({ queryVector: vector, keyword: text });
    renderResults(result);
    setStatus(
      els.searchStatus,
      `命中 ${result.ids.length} 条 · 查询向量化 ${embedMs.toFixed(0)} ms · seekdb 检索 ${result.searchMs.toFixed(0)} ms · 融合方式 ${result.usedRrf ? "RRF" : "分数相加"}${result.usedQueryLeg ? " · 含全文腿" : ""}`,
      "ok",
    );
  } catch (error) {
    setStatus(els.searchStatus, `检索失败：${(error as Error).message}`, "err");
  } finally {
    els.btnSearch.disabled = false;
  }
}

function renderResults(result: SearchResult) {
  els.results.innerHTML = "";
  if (!result.ids.length) {
    els.results.innerHTML = '<p class="hint">没有命中任何文档。</p>';
    return;
  }
  result.ids.forEach((id, index) => {
    const doc = result.documents[index] ?? "";
    const meta = result.metadatas[index] ?? {};
    const distance = result.distances[index];
    const item = document.createElement("div");
    item.className = "result";
    item.innerHTML = `
      <div class="result-head">
        <span class="result-rank">#${index + 1}</span>
        <span class="result-id">${escapeHtml(id)}</span>
        <span class="result-score">${typeof distance === "number" ? `dist ${distance.toFixed(4)}` : ""}</span>
      </div>
      <div class="result-body">${escapeHtml(doc)}</div>
      <div class="result-meta">${escapeHtml(JSON.stringify(meta))}</div>
    `;
    els.results.appendChild(item);
  });
}

function escapeHtml(value: string): string {
  return String(value).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch] ?? ch,
  );
}

// ---------------------------------------------------------------- 4. 证据
async function onSchema() {
  try {
    const schema = (await api.schema()) as Record<string, unknown>;
    showEvidence("seekdb 集合 / 表结构", schema);
  } catch (error) {
    setStatus(els.searchStatus, `读取表结构失败：${(error as Error).message}`, "err");
  }
}

async function onRows() {
  try {
    const rows = (await api.rows(20)) as Record<string, unknown>;
    showEvidence("seekdb 行级数据（原文 + 元数据）", rows);
  } catch (error) {
    setStatus(els.searchStatus, `读取行级数据失败：${(error as Error).message}`, "err");
  }
}

async function onReset() {
  try {
    await api.reset();
    setStatus(els.importStatus, "知识库已清空，回到初始状态（表为空）", "ok");
    els.results.innerHTML = "";
    showEvidence("初始状态", { note: "集合已重建，表内 0 行", at: new Date().toISOString() });
  } catch (error) {
    setStatus(els.importStatus, `清空失败：${(error as Error).message}`, "err");
  }
}

// ---------------------------------------------------------------- 5. 基准
async function loadCorpus() {
  if (corpusCache) return corpusCache;
  const response = await fetch("./bench/corpus.json");
  if (!response.ok) throw new Error(`语料读取失败：HTTP ${response.status}`);
  corpusCache = (await response.json()) as typeof corpusCache;
  return corpusCache!;
}

interface BenchRun {
  dtype: string;
  backend: string;
  loadMs: number;
  docEmbedMs: number;
  writeMs: number;
  refreshMs: number;
  results: {
    id: string;
    text: string;
    keyword: string;
    ids: string[];
    queryEmbedMs: number;
    searchMs: number;
  }[];
}

async function onBench() {
  els.btnBench.disabled = true;
  try {
    const corpus = await loadCorpus();
    const runs: BenchRun[] = [];

    for (const dtype of ["fp32", "fp16", "q8"] as Dtype[]) {
      setStatus(els.searchStatus, `基准：加载 ${dtype} 模型…`);
      const report = await loadEmbedder(dtype, { forceWasm: els.forceWasm.checked });

      // 每种精度用独立的集合，避免互相污染
      await api.reset();
      const chunks = corpus.docs.map((doc) => doc.text);
      const { vectors, embedMs } = await embedTexts(chunks, { batchSize: 16 });
      const write = await api.addDocuments({
        ids: corpus.docs.map((doc) => doc.id),
        documents: chunks,
        embeddings: vectors,
        metadatas: corpus.docs.map((doc) => ({ source: doc.id, topic: doc.topic ?? "" })),
      });

      const results: BenchRun["results"] = [];
      for (const query of corpus.queries) {
        const { vector, embedMs: queryEmbedMs } = await embedQuery(query.text);
        const search = await api.search({ queryVector: vector, keyword: query.keyword });
        results.push({
          id: query.id,
          text: query.text,
          keyword: query.keyword,
          ids: search.ids,
          queryEmbedMs,
          searchMs: search.searchMs,
        });
      }

      runs.push({
        dtype,
        backend: report.backend,
        loadMs: report.loadMs,
        docEmbedMs: embedMs,
        writeMs: write.writeMs,
        refreshMs: write.refreshMs,
        results,
      });
      setStatus(els.searchStatus, `基准：${dtype} 完成`);
    }

    const payload = {
      generatedAt: new Date().toISOString(),
      model: "Xenova/all-MiniLM-L6-v2",
      corpusSize: corpus.docs.length,
      queryCount: corpus.queries.length,
      forceWasm: els.forceWasm.checked,
      runs,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bench-raw-${payload.generatedAt.replace(/[:.]/g, "-")}.json`;
    link.click();
    URL.revokeObjectURL(url);
    showEvidence("基准原始数据（已下载）", payload);
    setStatus(els.searchStatus, "基准完成，原始 JSON 已下载", "ok");
  } catch (error) {
    setStatus(els.searchStatus, `基准失败：${(error as Error).message}`, "err");
  } finally {
    els.btnBench.disabled = false;
  }
}

// ---------------------------------------------------------------- 自动化钩子
// 给 Playwright / 手工脚本用：window.__kb.loadModel(...) 等
declare global {
  interface Window {
    __kb: {
      loadModel(dtype: Dtype, forceWasm?: boolean): Promise<unknown>;
      isReady(): boolean;
      backend(): string | null;
      modelName(): string | null;
      importDocs: (docs: { id: string; text: string }[]) => Promise<unknown>;
      importTexts(texts: string[]): Promise<unknown>;
      search(text: string, nResults?: number): Promise<SearchResult>;
      reset(): Promise<unknown>;
      bench(): Promise<unknown>;
    };
  }
}

window.__kb = {
  loadModel: (dtype, forceWasm = false) => loadEmbedder(dtype, { forceWasm }),
  isReady: () => getLoadReport() !== null,
  backend: () => getLoadReport()?.backend ?? null,
  modelName: () => getLoadReport()?.model ?? null,
  /** 按调用方给定的 id 写入 —— 基准脚本靠它把检索结果对回语料的 id，才能算 Recall@K。 */
  importDocs: async (docs: { id: string; text: string }[]) => {
    const { vectors, embedMs } = await embedTexts(
      docs.map((doc) => doc.text),
      { batchSize: 16 },
    );
    const write = await api.addDocuments({
      ids: docs.map((doc) => doc.id),
      documents: docs.map((doc) => doc.text),
      embeddings: vectors,
      metadatas: docs.map((doc) => ({ source: doc.id })),
    });
    return { ...write, embedMs };
  },
  importTexts: async (texts: string[]) => {
    const { vectors, embedMs } = await embedTexts(texts, { batchSize: 16 });
    const ids = texts.map((_, i) => `auto_${Date.now()}_${i}`);
    const write = await api.addDocuments({ ids, documents: texts, embeddings: vectors });
    return { ...write, embedMs };
  },
  search: async (text, nResults) => {
    const { vector, embedMs: queryEmbedMs } = await embedQuery(text);
    const result = await api.search({ queryVector: vector, keyword: text, nResults });
    return { ...result, queryEmbedMs };
  },
  reset: () => api.reset(),
  bench: onBench,
};

void init();
