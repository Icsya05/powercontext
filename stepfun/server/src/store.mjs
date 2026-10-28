/**
 * seekdb 数据访问层。
 *
 * 这个文件是整个服务端唯一接触数据库的地方，职责很窄：
 *   1. 写入浏览器已经算好的向量（原文 + 向量 + 元数据）
 *   2. 刷新索引（必需，否则向量检索返回空）
 *   3. 调用一次 hybridSearch()，把 seekdb 内部融合后的结果原样回传
 *
 * 它**不做**的事：不加载任何模型、不生成任何向量、不自己排序。
 * 排序由 seekdb 的 DBMS_HYBRID_SEARCH 在数据库内完成（见 README「混合检索如何由 seekdb 完成」）。
 */

import {
  SeekdbClient,
  SeekdbAdminClient,
  Schema,
  VectorIndexConfig,
  FulltextIndexConfig,
} from "seekdb";

import { config } from "./config.mjs";

let client = null;
let collection = null;
let collectionInfo = null;

/** 建库（已存在则忽略）。 */
export async function ensureDatabase() {
  const admin = new SeekdbAdminClient({
    host: config.seekdb.host,
    port: config.seekdb.port,
    user: config.seekdb.user,
    password: config.seekdb.password,
  });
  try {
    await admin.createDatabase(config.seekdb.database);
    return { created: true };
  } catch (error) {
    // 库已存在是正常情况
    return { created: false, reason: String(error?.message ?? error) };
  } finally {
    await admin.close().catch(() => {});
  }
}

/** 建集合：ik 中文全文索引 + VSAG HNSW 向量索引。embeddingFunction 必须为 null。 */
function buildSchema() {
  return new Schema({
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: config.seekdb.dimension, distance: config.seekdb.distance },
      // 端侧合规的关键：不让 SDK 在服务端调用任何 embedding 函数。
      embeddingFunction: null,
    }),
  });
}

export async function connect() {
  if (client) return { alreadyConnected: true };

  await ensureDatabase();

  client = new SeekdbClient({
    host: config.seekdb.host,
    port: config.seekdb.port,
    user: config.seekdb.user,
    password: config.seekdb.password,
    database: config.seekdb.database,
  });

  try {
    // 必须显式传 embeddingFunction: null。
    // SDK 的 resolveEmbeddingFunction() 在没有这个参数时会去加载「默认」embedding 函数
    // （@seekdb/default-embed），而那个包因为 workspace: 协议根本装不上，
    // 于是 getCollection() 会直接抛 "Embedding function 'default-embed' is not registered"。
    // 传 null 之后 SDK 会跳过默认函数，集合上不挂任何 embedding 函数 —— 这正是端侧方案需要的。
    collection = await client.getCollection({
      name: config.seekdb.collection,
      embeddingFunction: null,
    });

    // 维度对不上（例如换过 embedding 模型）时重建集合：
    // VECTOR(384) 的表插不进 512 维的向量。
    const info = await collection.describe().catch(() => null);
    if (info?.dimension && info.dimension !== config.seekdb.dimension) {
      await dropCollectionCompletely(config.seekdb.collection);
      collection = await client.createCollection({
        name: config.seekdb.collection,
        schema: buildSchema(),
      });
    }
  } catch (error) {
    // 集合不存在，或者「元数据在但物理表没了」（seekdb-js 的 deleteCollection 只删表不删元数据）。
    // 先清理残留元数据，再重建一个空集合。
    await dropStaleCollectionMetadata();
    try {
      collection = await client.createCollection({
        name: config.seekdb.collection,
        schema: buildSchema(),
      });
    } catch (createError) {
      throw new Error(
        `无法准备集合 ${config.seekdb.collection}：${createError?.message ?? createError}（原始错误：${error?.message ?? error}）`,
      );
    }
  }

  collectionInfo = await describeCollection();
  return { alreadyConnected: false, collection: collectionInfo };
}

/** 彻底删掉一个集合：物理表 + sdk_collections 里的元数据行。
 *  SDK 自带的 deleteCollection() 只删表不删元数据行，会留下「元数据在、表没了」的不一致状态。 */
async function dropCollectionCompletely(name) {
  const metas = await client.execute(
    "SELECT collection_id FROM sdk_collections WHERE collection_name = ?",
    [name],
  );
  for (const meta of metas ?? []) {
    const table = `c$v2$${meta.collection_id}`;
    await client.execute(`DROP TABLE IF EXISTS \`${table}\``).catch(() => {});
    await client.execute("DELETE FROM sdk_collections WHERE collection_id = ?", [
      meta.collection_id,
    ]);
  }
}

/** 清理 sdk_collections 里已经没有对应物理表的残留元数据。 */
async function dropStaleCollectionMetadata() {
  try {
    const tables = await client.execute(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = ? AND table_name LIKE 'c$v2$%'",
      [config.seekdb.database],
    );
    const liveIds = new Set((tables ?? []).map((row) => String(row.table_name).split("$").pop()));
    const metas = await client.execute(
      "SELECT collection_id, collection_name FROM sdk_collections",
    );
    for (const meta of metas ?? []) {
      if (!liveIds.has(String(meta.collection_id))) {
        await client.execute("DELETE FROM sdk_collections WHERE collection_id = ?", [
          meta.collection_id,
        ]);
      }
    }
  } catch {
    // 元数据表还不存在时忽略
  }
}

export async function disconnect() {
  if (client) {
    await client.close().catch(() => {});
    client = null;
    collection = null;
    collectionInfo = null;
  }
}

export function isConnected() {
  return Boolean(client && collection);
}

/**
 * 写入文档并刷新索引。
 *
 * @param {{ids: string[], documents: string[], embeddings: number[][], metadatas: object[]}} payload
 * @returns 写入与刷新的分段耗时，供 §3.2 的分阶段计时使用
 */
export async function addDocuments({ ids, documents, embeddings, metadatas }) {
  if (!collection) throw new Error("seekdb 尚未连接");

  const writeStart = performance.now();
  await collection.add({
    ids,
    documents,
    embeddings,
    metadatas: metadatas ?? ids.map(() => ({})),
  });
  const writeMs = performance.now() - writeStart;

  // 必须刷新：HNSW 索引是 SYNC_MODE=ASYNC，不刷新的话向量检索返回空。
  const refreshStart = performance.now();
  await collection.refresh_index();
  const refreshMs = performance.now() - refreshStart;

  const total = await collection.count();
  return { writeMs, refreshMs, total, inserted: ids.length };
}

/**
 * 混合检索：一次 hybridSearch() 调用，全文腿 + 向量腿的融合在 seekdb 内完成。
 *
 * @param {{queryVector: number[], keyword?: string, nResults?: number, useRRF?: boolean}} payload
 */
export async function search({ queryVector, keyword, nResults, useRRF }) {
  if (!collection) throw new Error("seekdb 尚未连接");

  const limit = nResults ?? config.search.defaultNResults;
  const candidates = Math.max(config.search.knnCandidates, limit);

  const options = {
    knn: {
      // 浏览器本地算好的查询向量，原样传给 seekdb
      queryEmbeddings: [queryVector],
      nResults: candidates,
    },
    nResults: limit,
  };

  if (keyword && keyword.trim()) {
    // 全文腿。注意：whereDocument 只约束全文腿，最终结果是两腿的并集（FULL JOIN）。
    options.query = {
      whereDocument: { $contains: keyword.trim() },
      nResults: candidates,
    };
  }

  if (useRRF ?? config.search.useRRF) {
    options.rank = {
      rrf: {
        rankWindowSize: config.search.rankWindowSize,
        rankConstant: config.search.rankConstant,
      },
    };
  }

  const start = performance.now();
  const result = await collection.hybridSearch(options);
  const searchMs = performance.now() - start;

  // query()/hybridSearch() 的返回是双层嵌套：第 0 层是查询组，第 1 层才是结果数组。
  const ids = result.ids?.[0] ?? [];
  const documents = result.documents?.[0] ?? [];
  const metadatas = result.metadatas?.[0] ?? [];
  const distances = result.distances?.[0] ?? [];

  return {
    ids,
    documents,
    metadatas,
    distances,
    searchMs,
    // 记录实际发给 seekdb 的参数，便于复现与取证
    usedQueryLeg: Boolean(keyword && keyword.trim()),
    usedRrf: Boolean(options.rank),
  };
}

/** 清空知识库，回到「初始状态」。 */
export async function reset() {
  if (!client) throw new Error("seekdb 尚未连接");

  // 不用 deleteCollection()：它只删物理表，不清理 sdk_collections 的元数据行，
  // 会让 SDK 处于「元数据在、表没了」的不一致状态。
  // 直接清空数据行即可 —— 表结构与索引保持不变，这正是可复现实验想要的初始状态。
  const table = await physicalTableName();
  let deleted = 0;
  if (table) {
    const result = await client.execute(`DELETE FROM \`${table}\``);
    deleted = result?.affectedRows ?? 0;
    await collection.refresh_index();
  } else {
    // 表还没建出来，直接重建一个空集合
    await dropStaleCollectionMetadata();
    collection = await client.createCollection({
      name: config.seekdb.collection,
      schema: buildSchema(),
    });
  }

  collectionInfo = await describeCollection();
  return { ok: true, deleted, collection: collectionInfo };
}

/** 找到集合对应的物理表名（SDK 命名为 c$v2$<collection_id>）。 */
async function physicalTableName() {
  const rows = await client.execute(
    "SELECT collection_id FROM sdk_collections WHERE collection_name = ? ORDER BY created_at DESC LIMIT 1",
    [config.seekdb.collection],
  );
  if (rows && rows.length && rows[0].collection_id) {
    return `c$v2$${rows[0].collection_id}`;
  }
  // 兜底：直接问 information_schema
  const tables = await client.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema = ? AND table_name LIKE 'c$v2$%'",
    [config.seekdb.database],
  );
  if (tables && tables.length) return tables[0].table_name;
  return null;
}

/**
 * 集合的物理结构：表 DDL、索引、行数、集合设置。
 * 这是 §4.2「seekdb 集合或表结构与索引配置」和 §3.1-5「行级数据证据」的数据来源。
 */
export async function schemaInfo() {
  if (!client) throw new Error("seekdb 尚未连接");
  const table = await physicalTableName();
  if (!table) return { ok: false, message: "集合的物理表还没建出来" };

  const ddlRows = await client.execute(`SHOW CREATE TABLE \`${table}\``);
  const indexRows = await client.execute(`SHOW INDEX FROM \`${table}\``);
  const countRows = await client.execute(`SELECT COUNT(*) AS n FROM \`${table}\``);
  const metaRows = await client.execute(
    "SELECT collection_id, collection_name, settings FROM sdk_collections WHERE collection_name = ? ORDER BY created_at DESC LIMIT 1",
    [config.seekdb.collection],
  );

  const rawSettings = metaRows?.[0]?.settings;
  let settings = null;
  if (rawSettings) {
    // mysql2 会自动把 JSON 列解析成对象；不同驱动/版本可能返回字符串。
    settings = typeof rawSettings === "string" ? JSON.parse(rawSettings) : rawSettings;
  }

  return {
    ok: true,
    database: config.seekdb.database,
    collection: config.seekdb.collection,
    table,
    rowCount: countRows?.[0]?.n ?? 0,
    ddl: ddlRows?.[0]?.["Create Table"] ?? ddlRows?.[0]?.["create table"] ?? null,
    indexes: (indexRows ?? []).map((row) => ({
      key: row.Key_name,
      column: row.Column_name,
      seq: row.Seq_in_index,
      type: row.Index_type,
      visible: row.Visible,
    })),
    settings,
  };
}

/** 导出前 N 行原文与元数据（行级证据，不含向量本体以免刷屏）。 */
export async function sampleRows(limit = 10) {
  if (!client) throw new Error("seekdb 尚未连接");
  const table = await physicalTableName();
  if (!table) return { ok: false, message: "还没有数据" };
  const rows = await client.execute(
    `SELECT _id, document, metadata FROM \`${table}\` LIMIT ${Number(limit)}`,
  );
  return {
    ok: true,
    table,
    rows: (rows ?? []).map((row) => ({
      id: Buffer.isBuffer(row._id) ? row._id.toString() : String(row._id),
      document: row.document,
      metadata: row.metadata ? (typeof row.metadata === "string" ? JSON.parse(row.metadata) : row.metadata) : null,
    })),
  };
}

async function describeCollection() {
  if (!collection) return null;
  const describe = await collection.describe().catch(() => null);
  const count = await collection.count().catch(() => 0);
  return { name: collection.name, describe, count };
}

export function getCollectionInfo() {
  return collectionInfo;
}
