/**
 * 服务端 API 端到端检查。
 *
 *   node scripts/check_api.mjs [baseUrl]
 *
 * 用**确定性伪随机向量**模拟浏览器算好的向量（服务端只负责转发），
 * 验证：写入 -> 索引刷新 -> 混合检索 -> 行级数据 -> 表结构 -> 重置。
 *
 * 注意：这里测的是**服务端与 seekdb 的链路**，不是浏览器里的推理。
 * 浏览器端的推理由 bench/ 与手工操作验证。
 */

const BASE = process.argv[2] ?? "http://127.0.0.1:8080";
// 向量维度从服务端读，不写死 —— 换 embedding 模型时维度会变（384 / 512）。
let DIM = 384;

const results = [];
function check(ok, label, detail = "") {
  results.push({ ok, label, detail });
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  ${detail}` : ""}`);
  return ok;
}

async function api(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  const text = await response.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { raw: text };
  }
  return { status: response.status, body };
}

function deterministicVector(seed, topic) {
  const vector = new Array(DIM);
  let state = seed;
  for (let i = 0; i < DIM; i += 1) {
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    vector[i] = state / 0x7fffffff - 0.5;
  }
  // 同 topic 的向量彼此更接近，不同 topic 更远 —— 这样混合检索的行为可预期
  for (let i = 0; i < DIM; i += 1) {
    vector[i] += 0.45 * Math.sin(i + topic * 7);
  }
  const norm = Math.sqrt(vector.reduce((sum, x) => sum + x * x, 0)) || 1;
  return vector.map((x) => x / norm);
}

const DOCS = [
  { id: "t1", topic: 1, text: "热牛奶在保温柜第二层，五块钱一瓶，扫码或者现金都行。" },
  { id: "t2", topic: 2, text: "关东煮的汤底每晚两点换一次，萝卜和海带最受欢迎。" },
  { id: "t3", topic: 3, text: "收银机下面压着一本账本，来过的客人会在上面留下字。" },
  { id: "t4", topic: 4, text: "凌晨三点整条街只剩这一家还亮着灯，玻璃上糊着热气。" },
  { id: "t5", topic: 1, text: "热牛奶要加热到四十度左右，不然太烫嘴。" },
];

console.log(`=== 服务端 API 端到端检查（${BASE}）===\n`);

// --- 0. 健康检查 ---
console.log("[0] 健康检查");
const health = await api("/api/health");
check(health.status === 200 && health.body.ok === true, "GET /api/health", `status=${health.status}`);
check(health.body.db?.connected === true, "seekdb 已连接", JSON.stringify(health.body.db ?? {}));
check(health.body.role === "transport-only", "服务端角色标记为 transport-only", `role=${health.body.role}`);
DIM = Number(health.body.db?.dimension ?? DIM);
check(Number.isInteger(DIM) && DIM > 0, "从服务端读到向量维度", `DIM=${DIM}`);

// --- 1. 重置到初始状态 ---
console.log("\n[1] 重置到初始状态");
const reset = await api("/api/reset", { method: "POST", body: "{}" });
check(reset.status === 200 && reset.body.ok === true, "POST /api/reset");

// --- 2. 写入 ---
console.log("\n[2] 写入文档（向量由调用方算好，服务端只转发）");
const write = await api("/api/documents", {
  method: "POST",
  body: JSON.stringify({
    ids: DOCS.map((d) => d.id),
    documents: DOCS.map((d) => d.text),
    embeddings: DOCS.map((d) => deterministicVector(42, d.topic)),
    metadatas: DOCS.map((d) => ({ topic: d.topic, source: "api-check" })),
  }),
});
check(write.status === 200 && write.body.ok === true, "POST /api/documents", JSON.stringify(write.body));
check(write.body.total === DOCS.length, "库内行数正确", `total=${write.body.total}`);
check(typeof write.body.refreshMs === "number" && write.body.refreshMs > 0, "返回了索引刷新耗时", `${write.body.refreshMs?.toFixed(1)} ms`);

// --- 3. 维度校验 ---
console.log("\n[3] 入参校验");
const badDim = await api("/api/documents", {
  method: "POST",
  body: JSON.stringify({ ids: ["x"], documents: ["x"], embeddings: [[1, 2, 3]] }),
});
check(badDim.status === 400, "维度不对时返回 400", `status=${badDim.status}`);
const badSearch = await api("/api/search", {
  method: "POST",
  body: JSON.stringify({ queryVector: [1, 2, 3] }),
});
check(badSearch.status === 400, "查询向量维度不对时返回 400", `status=${badSearch.status}`);

// --- 4. 混合检索 ---
console.log("\n[4] 混合检索");
const queryVector = deterministicVector(42, 1);
const search = await api("/api/search", {
  method: "POST",
  body: JSON.stringify({ queryVector, keyword: "热牛奶", nResults: 3 }),
});
check(search.status === 200 && search.body.ok === true, "POST /api/search", `status=${search.status}`);
check(Array.isArray(search.body.ids) && search.body.ids.length > 0, "返回了结果", JSON.stringify(search.body.ids));
check(search.body.usedQueryLeg === true, "启用了全文腿");
check(search.body.usedRrf === true, "使用了 RRF 融合");
check(search.body.ids.includes("t1") || search.body.ids.includes("t5"), "同 topic 的文档被召回", JSON.stringify(search.body.ids));
check(typeof search.body.searchMs === "number", "返回了检索耗时", `${search.body.searchMs?.toFixed(2)} ms`);
check(
  Array.isArray(search.body.documents) && search.body.documents.length === search.body.ids.length,
  "documents 与 ids 数量一致",
  `${search.body.documents?.length} vs ${search.body.ids?.length}`,
);

// --- 5. 表结构 ---
console.log("\n[5] 表结构与索引");
const schema = await api("/api/schema");
check(schema.status === 200 && schema.body.ok === true, "GET /api/schema");
const ddl = String(schema.body.ddl ?? "");
check(ddl.includes(`VECTOR(${DIM})`), `表里有 VECTOR(${DIM}) 列`);
check(/FULLTEXT KEY .*WITH PARSER ik/.test(ddl), "表里有 ik 全文索引");
check(/VECTOR KEY .*TYPE=HNSW/.test(ddl), "表里有 HNSW 向量索引");
check(schema.body.rowCount === DOCS.length, "行数正确", `rowCount=${schema.body.rowCount}`);

// --- 6. 行级数据 ---
console.log("\n[6] 行级数据（原文 + 元数据存在数据库里）");
const rows = await api("/api/rows?limit=10");
check(rows.status === 200 && rows.body.ok === true, "GET /api/rows");
check(rows.body.rows?.length === DOCS.length, "导出了全部行", `rows=${rows.body.rows?.length}`);
check(
  rows.body.rows?.every((row) => typeof row.document === "string" && row.document.length > 0),
  "每行都有原文",
);
check(rows.body.rows?.[0]?.metadata?.source === "api-check", "每行都有元数据", JSON.stringify(rows.body.rows?.[0]?.metadata));

// --- 7. 增量导入 ---
console.log("\n[7] 增量导入 + 刷新后可见");
const inc = await api("/api/documents", {
  method: "POST",
  body: JSON.stringify({
    ids: ["t6"],
    documents: ["新导入的文档：热牛奶今天卖得特别好。"],
    embeddings: [deterministicVector(42, 1)],
    metadatas: [{ topic: 1, source: "api-check" }],
  }),
});
check(inc.status === 200 && inc.body.ok === true, "增量写入成功", JSON.stringify(inc.body));
const afterInc = await api("/api/search", {
  method: "POST",
  body: JSON.stringify({ queryVector, keyword: "热牛奶", nResults: 5 }),
});
check(afterInc.body.ids?.includes("t6"), "增量文档刷新后可以被检索到", JSON.stringify(afterInc.body.ids));

// --- 8. 重置 ---
console.log("\n[8] 重置后回到初始状态");
const reset2 = await api("/api/reset", { method: "POST", body: "{}" });
check(reset2.status === 200 && reset2.body.ok === true, "再次重置成功");
const schema2 = await api("/api/schema");
check(schema2.body.rowCount === 0, "重置后表为空（初始状态）", `rowCount=${schema2.body.rowCount}`);

// --- 汇总 ---
const failed = results.filter((r) => !r.ok);
console.log(`\n=== 结果：${results.length - failed.length}/${results.length} 通过 ===`);
if (failed.length) {
  for (const item of failed) console.log(`  ! ${item.label} ${item.detail}`);
  process.exit(1);
}
console.log("服务端 API 端到端检查全部通过 ✅");
// Windows 上 undici 会把 keep-alive 连接留到进程退出，触发 libuv 断言崩溃。
// 检查已经跑完，显式退出即可。
process.exit(0);
