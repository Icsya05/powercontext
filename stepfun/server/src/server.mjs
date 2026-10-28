/**
 * 本地 HTTP 服务。
 *
 * 它只做两件事：
 *   1. 提供 API：接收浏览器已经算好的向量 -> 调 seekdb -> 原样回传结果
 *   2. 托管前端构建产物（web/dist），让评审一条命令就能跑起来
 *
 * 它**不做**推理：整个进程里没有任何模型、没有任何 embedding 依赖。
 * 浏览器算好向量后，服务器拿到的是一串浮点数，直接交给 seekdb。
 */

import http from "node:http";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { config, DEFAULTS } from "./config.mjs";
import {
  connect,
  disconnect,
  isConnected,
  addDocuments,
  search,
  reset,
  schemaInfo,
  sampleRows,
  getCollectionInfo,
} from "./store.mjs";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
};

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    // 允许 Vite dev server（5173）跨源访问本地 API。
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  });
  res.end(body);
}

function readBody(req, limitBytes = 64 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limitBytes) {
        reject(new Error("请求体过大"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`请求体不是合法 JSON: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
}

async function serveStatic(req, res, urlPath) {
  const root = config.http.webRoot;
  const relative = urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "");
  const target = path.resolve(root, relative);

  // 防目录穿越
  if (!target.startsWith(path.resolve(root))) {
    sendJson(res, 403, { ok: false, message: "非法路径" });
    return;
  }

  let filePath = target;
  const stat = await fsp.stat(filePath).catch(() => null);
  if (!stat || stat.isDirectory()) {
    filePath = path.join(root, "index.html");
  }
  const finalStat = await fsp.stat(filePath).catch(() => null);
  if (!finalStat) {
    sendJson(res, 404, {
      ok: false,
      message: "前端还没构建。先跑 `node scripts/build-web.mjs`（或 pnpm build）。",
      webRoot: root,
    });
    return;
  }

  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, {
    "Content-Type": MIME[ext] ?? "application/octet-stream",
    "Content-Length": finalStat.size,
    "Cache-Control": ext === ".html" ? "no-store" : "public, max-age=3600",
  });
  fs.createReadStream(filePath).pipe(res);
}

export function createServer() {
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);
    const { pathname } = url;

    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      });
      res.end();
      return;
    }

    try {
      // ---------------- API ----------------
      if (pathname === "/api/health") {
        sendJson(res, 200, {
          ok: true,
          service: "stepfun-kb-server",
          role: "transport-only",
          note: "服务端不做推理：向量由浏览器在本地计算，排序由 seekdb 在数据库内完成",
          db: {
            connected: isConnected(),
            host: config.seekdb.host,
            port: config.seekdb.port,
            database: config.seekdb.database,
            collection: config.seekdb.collection,
            dimension: config.seekdb.dimension,
          },
          collection: getCollectionInfo(),
        });
        return;
      }

      if (pathname === "/api/documents" && req.method === "POST") {
        const body = await readBody(req);
        const { ids, documents, embeddings, metadatas } = body ?? {};
        if (!Array.isArray(ids) || !Array.isArray(documents) || !Array.isArray(embeddings)) {
          sendJson(res, 400, {
            ok: false,
            message: "需要 ids / documents / embeddings 三个数组",
          });
          return;
        }
        if (ids.length !== documents.length || ids.length !== embeddings.length) {
          sendJson(res, 400, { ok: false, message: "ids / documents / embeddings 长度必须一致" });
          return;
        }
        for (const vector of embeddings) {
          if (!Array.isArray(vector) || vector.length !== config.seekdb.dimension) {
            sendJson(res, 400, {
              ok: false,
              message: `每条向量必须是长度 ${config.seekdb.dimension} 的数组`,
            });
            return;
          }
        }
        const result = await addDocuments({ ids, documents, embeddings, metadatas });
        sendJson(res, 200, { ok: true, ...result });
        return;
      }

      if (pathname === "/api/search" && req.method === "POST") {
        const body = await readBody(req);
        const { queryVector, keyword, nResults, useRRF } = body ?? {};
        if (!Array.isArray(queryVector) || queryVector.length !== config.seekdb.dimension) {
          sendJson(res, 400, {
            ok: false,
            message: `queryVector 必须是长度 ${config.seekdb.dimension} 的数组（浏览器本地计算）`,
          });
          return;
        }
        const result = await search({ queryVector, keyword, nResults, useRRF });
        sendJson(res, 200, { ok: true, ...result });
        return;
      }

      if (pathname === "/api/reset" && req.method === "POST") {
        sendJson(res, 200, { ok: true, ...(await reset()) });
        return;
      }

      if (pathname === "/api/schema") {
        sendJson(res, 200, await schemaInfo());
        return;
      }

      if (pathname === "/api/rows") {
        const limit = Number(url.searchParams.get("limit") ?? 10);
        sendJson(res, 200, await sampleRows(limit));
        return;
      }

      if (pathname === "/api/config") {
        sendJson(res, 200, {
          ok: true,
          dimension: DEFAULTS.dimension,
          model: DEFAULTS.model,
          distance: config.seekdb.distance,
          knnCandidates: config.search.knnCandidates,
          useRRF: config.search.useRRF,
          rankWindowSize: config.search.rankWindowSize,
          rankConstant: config.search.rankConstant,
        });
        return;
      }

      if (pathname.startsWith("/api/")) {
        sendJson(res, 404, { ok: false, message: `未知接口 ${pathname}` });
        return;
      }

      // ---------------- 静态资源 ----------------
      if (req.method === "GET") {
        await serveStatic(req, res, pathname);
        return;
      }

      sendJson(res, 405, { ok: false, message: "不支持的方法" });
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        message: String(error?.message ?? error),
        stack: String(error?.stack ?? "").split("\n").slice(0, 6),
      });
    }
  });
}

export async function start() {
  await connect();
  const server = createServer();
  await new Promise((resolve) => {
    server.listen(config.http.port, config.http.host, resolve);
  });
  const webExists = fs.existsSync(path.join(config.http.webRoot, "index.html"));
  console.log(`[stepfun] 服务端已启动  http://${config.http.host}:${config.http.port}`);
  console.log(`[stepfun] seekdb        ${config.seekdb.host}:${config.seekdb.port}/${config.seekdb.database} 集合=${config.seekdb.collection}`);
  console.log(`[stepfun] 前端          ${webExists ? config.http.webRoot : "未构建（开发模式请另开 vite dev server）"}`);
  console.log("[stepfun] 服务端零推理：向量来自浏览器，排序来自 seekdb");
  return server;
}

export async function stop(server) {
  await new Promise((resolve) => server?.close(resolve));
  await disconnect();
}
