/**
 * 与本地服务端交互。
 *
 * 注意：这里传的是**浏览器已经算好的向量**，服务端不参与计算。
 */

export interface SearchResult {
  ids: string[];
  documents: string[];
  metadatas: Record<string, unknown>[];
  distances: number[];
  searchMs: number;
  usedQueryLeg: boolean;
  usedRrf: boolean;
  /** 浏览器本地生成查询向量的耗时（由页面侧补上）。 */
  queryEmbedMs?: number;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.message ?? `请求失败：HTTP ${response.status}`);
  }
  return data as T;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.message ?? `请求失败：HTTP ${response.status}`);
  }
  return data as T;
}

export interface HealthInfo {
  ok: boolean;
  role: string;
  note: string;
  db: {
    connected: boolean;
    host: string;
    port: number;
    database: string;
    collection: string;
    dimension: number;
  };
}

export const api = {
  health: () => get<HealthInfo>("/api/health"),
  config: () => get<Record<string, unknown>>("/api/config"),
  schema: () => get<Record<string, unknown>>("/api/schema"),
  rows: (limit = 10) => get<Record<string, unknown>>(`/api/rows?limit=${limit}`),
  reset: () => post<Record<string, unknown>>("/api/reset", {}),
  addDocuments: (payload: {
    ids: string[];
    documents: string[];
    embeddings: number[][];
    metadatas?: Record<string, unknown>[];
  }) =>
    post<{ ok: true; writeMs: number; refreshMs: number; total: number; inserted: number }>(
      "/api/documents",
      payload,
    ),
  search: (payload: { queryVector: number[]; keyword?: string; nResults?: number; useRRF?: boolean }) =>
    post<SearchResult>("/api/search", payload),
};
