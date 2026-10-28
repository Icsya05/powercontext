/**
 * 端侧 embedding 推理。
 *
 * 这个模块是整个作品里**唯一**做推理的地方，而且它运行在浏览器里。
 * 服务端（server/）里没有对应实现，也没有对应的依赖。
 *
 * 关键点：
 *  1. 文档向量化与查询向量化走同一条路径、同一个模型、同一套预处理
 *     （mean pooling + L2 归一化），这样余弦距离才有意义。
 *  2. 优先 WebGPU；拿不到 adapter 就自动降级 WASM，并把当前后端暴露给界面。
 *  3. dtype 决定加载哪个 ONNX 变体：fp32 / fp16 / q8 / int8 / uint8 / q4。
 */

import { pipeline, env } from "@huggingface/transformers";

export const MODEL_ID = "Xenova/bge-small-zh-v1.5";

/**
 * 每个模型对应的池化方式与输出维度。
 * - bge-small-zh-v1.5：中文效果远好于 all-MiniLM（后者偏英文），官方推荐 CLS 池化，512 维
 * - all-MiniLM-L6-v2：官方推荐 mean 池化，384 维
 * 维度必须和 seekdb 建集合时的 hnsw.dimension 一致，否则写入会报错。
 */
export const MODEL_SPECS: Record<string, { pooling: "mean" | "cls"; dimension: number }> = {
  "Xenova/bge-small-zh-v1.5": { pooling: "cls", dimension: 512 },
  "Xenova/all-MiniLM-L6-v2": { pooling: "mean", dimension: 384 },
};

export function specFor(model: string) {
  return MODEL_SPECS[model] ?? { pooling: "mean" as const, dimension: 384 };
}

/** Transformers.js 的 dtype -> ONNX 文件后缀映射（与官方 DEFAULT_DTYPE_SUFFIX_MAPPING 一致）。 */
export const DTYPE_SUFFIX = {
  fp32: "",
  fp16: "_fp16",
  q8: "_quantized",
  int8: "_int8",
  uint8: "_uint8",
  q4: "_q4",
  q4f16: "_q4f16",
  bnb4: "_bnb4",
} as const;

export const DTYPE_OPTIONS = [
  { value: "fp32", label: "fp32（基线）", note: "onnx/model.onnx" },
  { value: "fp16", label: "fp16", note: "onnx/model_fp16.onnx" },
  { value: "q8", label: "q8 / int8 量化", note: "onnx/model_quantized.onnx" },
  { value: "int8", label: "int8", note: "onnx/model_int8.onnx" },
  { value: "uint8", label: "uint8", note: "onnx/model_uint8.onnx" },
] as const;

export type Dtype = keyof typeof DTYPE_SUFFIX;
export type Backend = "webgpu" | "wasm";

/** onnxruntime-web 的 wasm 从本地 /ort/ 取，避免依赖 CDN（离线可跑）。 */
env.allowLocalModels = true;
env.useBrowserCache = true;
// 模型优先从本地 /models/<repo>/ 取（由 scripts/fetch-model.mjs 预置），
// 取不到再回落到 Hugging Face 官方仓库。
env.localModelPath = "/models/";
env.remoteHost = "https://huggingface.co";
env.remotePathTemplate = "{model}/resolve/{revision}/";
// @ts-expect-error 不同版本字段位置略有差异
env.backends.onnx.wasm.wasmPaths = new URL("ort/", document.baseURI).href;
// 单线程：不要求 COOP/COEP 跨源隔离，评审用普通方式起服务也能跑。
// @ts-expect-error 同上
env.backends.onnx.wasm.numThreads = 1;

export interface BackendProbe {
  hasNavigatorGpu: boolean;
  adapter: boolean;
  reason: string;
}

/** 探测 WebGPU 是否真的可用（navigator.gpu 存在 != 能拿到适配器）。 */
export async function probeWebGPU(): Promise<BackendProbe> {
  const nav = navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } };
  if (!nav.gpu) {
    return { hasNavigatorGpu: false, adapter: false, reason: "浏览器没有暴露 navigator.gpu" };
  }
  try {
    const adapter = await nav.gpu.requestAdapter();
    if (!adapter) {
      return { hasNavigatorGpu: true, adapter: false, reason: "navigator.gpu.requestAdapter() 返回 null" };
    }
    return { hasNavigatorGpu: true, adapter: true, reason: "WebGPU 适配器可用" };
  } catch (error) {
    return {
      hasNavigatorGpu: true,
      adapter: false,
      reason: `requestAdapter() 抛错: ${String(error)}`,
    };
  }
}

export interface LoadReport {
  backend: Backend;
  dtype: Dtype;
  model: string;
  loadMs: number;
  /** 模型文件大致体积（字节），来自响应头的 content-length 累加。 */
  bytes: number;
  note: string;
}

type Extractor = Awaited<ReturnType<typeof pipeline<"feature-extraction">>>;

let extractor: Extractor | null = null;
let loaded: LoadReport | null = null;

/**
 * 加载（或热切换）embedding 模型。
 * forceWasm=true 时即使 WebGPU 可用也强制走 WASM —— 这是给「验证降级路径」用的。
 */
export async function loadEmbedder(
  dtype: Dtype = "fp32",
  options: { forceWasm?: boolean; model?: string } = {},
): Promise<LoadReport> {
  const model = options.model ?? MODEL_ID;
  const probe = await probeWebGPU();

  let backend: Backend;
  let note: string;
  if (options.forceWasm) {
    backend = "wasm";
    note = "已按要求强制降级到 WASM";
  } else if (probe.adapter) {
    backend = "webgpu";
    note = probe.reason;
  } else {
    backend = "wasm";
    note = `自动降级到 WASM（${probe.reason}）`;
  }

  const start = performance.now();
  extractor = await pipeline("feature-extraction", model, {
    device: backend,
    dtype,
  });
  const loadMs = performance.now() - start;

  loaded = {
    backend,
    dtype,
    model,
    loadMs,
    bytes: 0,
    note,
  };
  return loaded;
}

export function getLoadReport(): LoadReport | null {
  return loaded;
}

/** 把一段文本切成句子级片段（中文按标点切，英文按句号切）。 */
export function chunkText(text: string, maxChars = 320): string[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const pieces = normalized
    .split(/(?<=[。！？!?；;\n])/)
    .map((piece) => piece.trim())
    .filter(Boolean);

  const chunks: string[] = [];
  let buffer = "";
  for (const piece of pieces) {
    if (buffer.length + piece.length > maxChars && buffer) {
      chunks.push(buffer);
      buffer = piece;
    } else {
      buffer += (buffer ? " " : "") + piece;
    }
  }
  if (buffer) chunks.push(buffer);
  return chunks.length ? chunks : [normalized];
}

/** 批量向量化。返回与输入等长的 number[][]（按模型要求池化 + L2 归一化）。 */
export async function embedTexts(
  texts: string[],
  options: { batchSize?: number } = {},
): Promise<{ vectors: number[][]; embedMs: number; perTextMs: number[] }> {
  if (!extractor) throw new Error("模型还没加载，请先点「加载模型」");
  if (!texts.length) return { vectors: [], embedMs: 0, perTextMs: [] };

  const batchSize = options.batchSize ?? 16;
  const vectors: number[][] = [];
  const perTextMs: number[] = [];
  const start = performance.now();
  const pooling = specFor(loaded?.model ?? MODEL_ID).pooling;

  for (let offset = 0; offset < texts.length; offset += batchSize) {
    const batch = texts.slice(offset, offset + batchSize);
    const batchStart = performance.now();
    const output = await extractor(batch, { pooling, normalize: true });
    const list = output.tolist() as number[][];
    for (const vector of list) vectors.push(vector);
    const perBatch = (performance.now() - batchStart) / batch.length;
    for (let i = 0; i < batch.length; i += 1) perTextMs.push(perBatch);
  }

  const embedMs = performance.now() - start;
  return { vectors, embedMs, perTextMs };
}

/** 单条向量化（查询用）。 */
export async function embedQuery(text: string): Promise<{ vector: number[]; embedMs: number }> {
  const { vectors, embedMs } = await embedTexts([text]);
  return { vector: vectors[0], embedMs };
}
