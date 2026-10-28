/**
 * 服务端配置。所有值都可以用环境变量覆盖。
 *
 * 这个文件里不会出现任何模型名或 embedding 依赖 —— 服务端不做推理。
 */

import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));

const num = (value, fallback) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const config = {
  // --- seekdb 连接（服务端模式，跨平台最稳） ---
  seekdb: {
    host: process.env.SEEKDB_HOST ?? "127.0.0.1",
    port: num(process.env.SEEKDB_PORT, 28811),
    user: process.env.SEEKDB_USER ?? "root",
    password: process.env.SEEKDB_PASSWORD ?? "StepFun@2026",
    database: process.env.SEEKDB_DATABASE ?? "stepfun_kb",
    collection: process.env.SEEKDB_COLLECTION ?? "kb",
    dimension: num(process.env.SEEKDB_DIMENSION, 512),
    distance: process.env.SEEKDB_DISTANCE ?? "cosine",
  },

  // --- 本地 HTTP 服务 ---
  http: {
    host: process.env.HOST ?? "127.0.0.1",
    port: num(process.env.PORT, 8080),
    // 前端构建产物目录。存在就托管，不存在就只提供 API（开发时用 Vite dev server）。
    // 注意 here = server/src，所以要回两级才是 stepfun/。
    webRoot: process.env.WEB_ROOT ?? path.resolve(here, "..", "..", "web", "dist"),
  },

  // --- 检索参数 ---
  search: {
    defaultNResults: num(process.env.SEARCH_NRESULTS, 10),
    // 向量腿的候选数。至少要 >= 最终返回条数，否则混合后条数不足。
    knnCandidates: num(process.env.SEARCH_KNN_CANDIDATES, 30),
    // RRF 参数。默认开启：两腿分数量纲不同（全文分 ~0.3，向量分 ~0.5），RRF 更稳。
    useRRF: (process.env.SEARCH_USE_RRF ?? "1") !== "0",
    rankWindowSize: num(process.env.SEARCH_RRF_WINDOW, 60),
    rankConstant: num(process.env.SEARCH_RRF_CONSTANT, 60),
  },
};

export const DEFAULTS = {
  model: process.env.EMBED_MODEL ?? "Xenova/bge-small-zh-v1.5",
  dimension: config.seekdb.dimension,
};
