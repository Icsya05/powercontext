# 阶段 0 实测结论 —— 把「假设」变成「事实」

> 作者：zyj　｜　日期：2026-10-28 23:5x　｜　机台：D:\ZhuYijing\Documents\minimax工作文件夹
> 探针目录：`D:\Tools\stepfun-probe`（不在仓库内）
> 本文件接在 `STATE_AND_HANDOFF.md` 之后：那一份列了 8 条未验证假设，**这份逐条给出实测结果**。
> 下面每一条结论都有真实命令输出支撑，不是推断。

---

## 0. 一句话结论

**8 条未验证假设里，5 条已变成事实（假设 1/2/4/5 已解决，假设 3 已被否证并给出替代方案），3 条仍未验证（浏览器下载模型、Playwright、WebGPU 真跑）。**
最关键的一条：**混合检索确实由 seekdb 内部完成**（§2.3.2 红线成立），但机制和 README 写的不一样，必须按本文的说明实现。

---

## 1. 安装：npm 不行，pnpm 行（假设 5 前半）

### 1.1 `npm install seekdb` 确实失败 —— 复现成功

```
$ npm.cmd install seekdb
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
```

`--omit=optional` **也救不了**（同样报错）。

### 1.2 根因定位（精确）

发布的 `seekdb@1.4.0` tarball 本身是干净的：

```json
"dependencies":       { "mysql2": "^3.11.5" },
"optionalDependencies": { "@seekdb/js-bindings": "1.4.0" },
"peerDependencies":   { "@seekdb/default-embed": "^1.2.0" }
```

`workspace:*` 来自**嵌套包** `@seekdb/js-bindings` 的依赖声明 —— lerna 发包时没有把 workspace 协议重写掉。这是 **seekdb-js 上游的发布缺陷**，不是我们的问题，但**评审复现时会踩到，必须写进 README**。

### 1.3 pnpm 可以装

```
$ corepack pnpm add seekdb
dependencies:
+ seekdb 1.4.0
Done in 20.9s using pnpm v12.16.1
```

### 1.4 ⚠️ pnpm 12 新坑：build scripts 必须显式批准

```
$ corepack pnpm add @huggingface/transformers
╰─▶ Ignored build scripts: onnxruntime-node@1.30.0, protobufjs@7.6.6
   help: Run "pnpm approve-builds" to pick which dependencies should be allowed to run scripts.
ERR_PNPM_IGNORED_BUILDS
```

**本项目是浏览器应用，不需要 `onnxruntime-node` 的原生构建**，所以直接：

```bash
corepack pnpm add --ignore-scripts @huggingface/transformers
```

### 1.5 `@seekdb/bm25` 装不上 —— 假设 3 被否证

发布的 tarball 里：

```json
"peerDependencies": {
  "@seekdb/common": "workspace:*",
  "seekdb": "workspace:*"
}
```

**npm 和 pnpm 都拒绝解析**：

```
╰─▶ Failed to resolve dependency: Cannot resolve @seekdb/common@workspace:*
```

（npm 上 `@seekdb/common` 最新只有 1.2.0，和 1.4.0 对不上。）

> ### 决策：放弃 BM25 第三路稀疏检索
> 题面 §2.3.2 只要求「向量 + 全文混合检索」，**没有要求三路**。
> 已验证可用的 **稠密向量 + ik 全文两路混合**（见第 3 节）完全满足要求。
> `@seekdb/bm25` 装不上 → 不在依赖里，避免评审装不上直接卡死。

---

## 2. 导出与 API 签名（假设 1 → 事实）

`seekdb@1.4.0` 共 33 个导出，**关键 7 个全部存在**：

```
OK  SeekdbClient      OK  Schema
OK  SeekdbAdminClient OK  VectorIndexConfig
OK  FulltextIndexConfig
OK  SparseVectorIndexConfig
OK  Key
OK  K
```

### 2.1 ⚠️ `K` 和 `Key` 不等价 —— README 写错了

```js
typeof K  = function
typeof Key = function
K === Key ? false
Key.DOCUMENT  = {"name":"#document"}
Key.EMBEDDING = {"name":"#embedding"}
```

**运行时必须用 `Key.DOCUMENT` / `Key.EMBEDDING`**，不能照 README 写 `K.DOCUMENT`。

### 2.2 Collection 的全部公开方法（从 d.ts 提取）

```ts
add(options: AddOptions): Promise<void>
update(options: UpdateOptions): Promise<void>
upsert(options: UpsertOptions): Promise<void>
delete(options: DeleteOptions): Promise<void>
get<TMeta>(options?: GetOptions): Promise<GetResult<TMeta>>
query<TMeta>(options: QueryOptions): Promise<QueryResult<TMeta>>
hybridSearch<TMeta>(options: HybridSearchOptions): Promise<QueryResult<TMeta>>
fork(options: ForkOptions): Promise<Collection>
count(): Promise<number>
refresh_index(): Promise<void>          // ← 关键，见第 4 节
describe(): Promise<{name; dimension; distance}>
peek<TMeta>(limit?: number): Promise<GetResult<TMeta>>
```

### 2.3 ⚠️ 两个不可靠的 API，别用

| API | 实测行为 | 结论 |
|---|---|---|
| `client.listCollections()` | 集合明明存在，**返回 `[]`** | **不可用**，别拿它做知识库列表 |
| `collection.describe()` | 只返回 `{name, dimension, distance}` | 没有索引信息，要看索引直接查 SQL |

---

## 3. 混合检索的真实机制（假设 2 → 事实，且与 README 不同）★核心

### 3.1 SDK 干了什么

```js
// 1) 把参数塞进一个 JSON
searchParm = { query: {...}, knn: {...}, rank?: {...}, size: nResults }

// 2) 交给 seekdb 内部的存储过程生成 SQL
SET @search_parm = '<json>'
SELECT DBMS_HYBRID_SEARCH.GET_SQL('<表名>', @search_parm) as query_sql FROM dual

// 3) 执行生成的 SQL
```

`search_parm` 的精确结构（从 SDK 源码提取）：

```json
{
  "query": { "query_string": { "fields": ["document"], "query": "账本" } },
  "knn":   { "field": "embedding", "k": 3, "query_vector": [ ... ] },
  "rank":  { "rrf": { "rank_window_size": 60, "rank_constant": 60 } },
  "size":  3
}
```

### 3.2 seekdb 生成的真实 SQL（实测原文）

```sql
SELECT ifnull(`_fts`.`_id`, `_vs`.`_id`) as `_id`,
       ... ,
       (ifnull(`_fts`.`_keyword_score`, 0) + ifnull(`_vs`.`_semantic_score`, 0)) as `_score`
FROM (
  -- 全文腿
  SELECT `__pk_increment`, `_id`, `document`, `embedding`, `metadata`,
         match(`document`) against('账本' in natural language mode) as `_keyword_score`
  FROM `stepfun_probe2`.`c$v2$9c45...`
  WHERE match(`document`) against('账本' in natural language mode)
  ORDER BY `_keyword_score` DESC LIMIT 60
) `_fts`
FULL JOIN (
  -- 向量腿
  SELECT `__pk_increment`, `_id`, `document`, `embedding`, `metadata`,
         round(1 - cosine_distance(`embedding`, '[...]') / 2, 8) as `_semantic_score`
  FROM `stepfun_probe2`.`c$v2$9c45...`
  ORDER BY cosine_distance(`embedding`, '[...]') APPROXIMATE LIMIT 3
) `_vs`
ON `_fts`.`__pk_increment` = `_vs`.`__pk_increment`
ORDER BY `_score` DESC, ifnull(`_vs`.`__pk_increment`, `_fts`.`__pk_increment`) LIMIT 3
```

### 3.3 三条必须记住的结论

1. **✅ §2.3.2 红线成立**：两腿的融合（`FULL JOIN` + 加权）在 **seekdb 数据库内**完成。前端只发一次请求、只收一次结果，**完全合规**。
2. **融合方式**：
   - 默认 = **分数相加**（`_keyword_score + _semantic_score`）
   - 传 `rank: { rrf: { rankWindowSize, rankConstant } }` → 改用 **RRF**：`1/(rank+60) + 1/(rank+60)`
   - 建议显式传 RRF —— 加权相加时两腿分数量纲不一致（全文分 0.31、向量分 0.51），RRF 更稳。
3. **⚠️ `whereDocument` 不是「过滤整个结果集」，只作用于全文腿**：
   - `FULL JOIN` 是外连接 → 不含关键词的文档也会从向量腿进来，只是 `_keyword_score` 为 0。
   - 实测：`$contains:"账本"` 时全文腿只命中 d3/d5，但最终结果是 d3/d2/d5（d2 来自向量腿）。
   - **这不是 bug，是设计**。但前端展示时要知道：**搜"账本"也会返回不含"账本"的文档**。若产品上需要硬过滤，应在拿到结果后按全文分再筛一次，或用 `whereDocument.$and/$or` 组合。

### 3.4 实测结果（4 条文档 + 1 条增量）

| 调用 | 结果 | 耗时 |
|---|---|---|
| `query({queryEmbeddings:[v], nResults:3})`（刷新后） | `[["d3","d1","d2"]]` | 7.0 ms |
| `hybridSearch({query:{whereDocument:{$contains:"账本"}}, knn:{queryEmbeddings:[v]}, nResults:3})` | `[["d3","d2","d5"]]` | 67.0 ms |
| `hybridSearch({knn:{queryEmbeddings:[v]}, nResults:3})`（无全文腿对照） | `[["d2","d4","d3"]]` | — |
| 全文腿单独（GET_SQL 生成的 SQL 手工执行） | d5(0.366) / d3(0.311) | — |

**全文腿确实生效**：单独跑全文腿只返回含"账本"的 d5 和 d3，与文档完全一致 ✅

### 3.5 ⚠️ `$contains` 的值里不要带 `%`

SDK 会把值原样拼进 `against('<值>' in natural language mode)`。值里带 `%` 会生成 `against('%账本%' ...)`，在 Python 驱动里 `%` 被当占位符 → `not enough arguments for format string`。用纯词即可。

---

## 4. ★ 索引刷新是必须的（§2.3.3）

```
--- add() 完成 ---
count()                 = 4
query() 刷新【前】       = [[]]          ← 空！
--- refresh_index() ---
  耗时 714.4 ms
--- 刷新后 ---
count()                 = 4
query() 刷新【后】       = [["d3","d1","d2"]]
```

**结论**：

- `collection.add()` 之后**必须** `await collection.refresh_index()`，否则向量检索返回空。
- `count()` 在刷新前就正确（行已经写进去了），**只有索引没建好**。
- 714 ms 是 4 条数据的刷新耗时 —— 这是 §3.2 要求的「写入与索引刷新」计时项的**基线量级**，正式测要按真实语料规模重测。

---

## 5. 真实表结构（§4.2「集合或表结构与索引配置」直接抄）

SDK 为每个集合建一张表，表名 = `c$v2$<collection_id>`；集合设置另存在 `sdk_collections`。

```sql
CREATE TABLE `c$v2$9c456663d2e311f189bceacd27caeb0c` (
  `_id`        varbinary(512) NOT NULL,
  `document`   string DEFAULT NULL,
  `embedding`  VECTOR(384) DEFAULT NULL,
  `metadata`   json DEFAULT NULL,
  PRIMARY KEY (`_id`),
  FULLTEXT KEY `idx_fts` (`document`)
      WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart") BLOCK_SIZE 16384,
  VECTOR KEY `idx_vec` (`embedding`)
      WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, M=16, EF_CONSTRUCTION=200,
            EF_SEARCH=64, SYNC_MODE=ASYNC) BLOCK_SIZE 16384
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4
  ROW_FORMAT = DYNAMIC COMPRESSION = 'zstd_1.3.8'
  BLOCK_SIZE = 16384 TABLET_SIZE = 134217728 PCTFREE = 0;
```

```sql
CREATE TABLE `sdk_collections` (
  `collection_id`   char(32) NOT NULL DEFAULT (replace(uuid(),'-','')),
  `collection_name` string DEFAULT NULL,
  `settings`        json DEFAULT NULL COMMENT 'Generated by SDK, don\'t modify',
  `created_at`      timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`collection_id`),
  UNIQUE KEY `idx_name` (`collection_name`) BLOCK_SIZE 16384 LOCAL
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4;
```

`settings` 实际内容：

```json
{"schema":{"vectorIndex":{"hnsw":{"distance":"cosine","dimension":384}},
           "fulltextIndex":{"analyzer":"ik","properties":{"ik_mode":"smart"}}},
 "version":"v2"}
```

**重点**：
- 索引**全部由 SDK 自动建好**：ik 全文索引 + VSAG HNSW 向量索引（`SYNC_MODE=ASYNC` → 这就是必须刷新的原因）。
- **表名带 `$`**，用 mysql CLI 查询时要做转义（`c$v2$...`），**用 pymysql 或 SDK 访问没这个问题**（本次就是踩了这个坑）。
- 维度 384 与 `all-MiniLM-L6-v2` 一致 ✅

### 5.1 底层 SQL 直接可用（用于证据导出与自定义查询）

```sql
-- 全文（带分数）
select _id, match(document) against('%账本%' in natural language mode) as score
from `c$v2$...` where match(document) against('%账本%' in natural language mode);

-- 向量（VSAG 余弦距离）
select _id, l2_distance(embedding, '[...]') as dist from `c$v2$...` order by dist limit 3;
```

实测：`MATCH AGAINST` 精确命中 d5(0.366)/d3(0.311)；`l2_distance` 正常返回。**这两条可以直接用于 §3.1-5 的「行级数据证据」。**

---

## 6. 返回结构不一致（前端必须处理）

| API | `ids` 形状 | 说明 |
|---|---|---|
| `query()` | `[["d3","d1","d2"]]` | **双层嵌套**（外层=查询组，内层=命中 id 数组） |
| `hybridSearch()` | `[["d3","d2","d5"]]` | **双层嵌套** |
| `get({ids})` | `["d1","d3"]` | **单层** |
| `peek(limit)` | 同 `get`，单层 | |

`query`/`hybridSearch` 的 `distances` / `documents` / `metadatas` 同样是双层。
**踩坑提示**：用 `String(result.documents[0])` 打印会「看起来正常」，因为数组转字符串会 join —— 很容易误判成单层。**用 `Array.isArray(result.ids[0])` 判断。**

---

## 7. 端侧推理栈（假设 4 → 事实）

### 7.1 Transformers.js

```
@huggingface/transformers 4.3.1   （已装；npm 上最新 4.3.2）
```

**dtype 选项名**（官方类型文档原文）：

```
['fp32', 'fp16', 'int8', 'uint8', 'q8', 'q4']
```

**device 选项名**：

```ts
export const DEVICE_TYPES: Readonly<{ wasm: "wasm"; webgpu: "webgpu"; ... }>;
export type DeviceType = keyof typeof DEVICE_TYPES;
```

→ `pipeline('feature-extraction', model, { device: 'webgpu', dtype: 'fp32' })`，降级用 `device: 'wasm'` + `dtype: 'q8'`。

### 7.2 量化对照组（同一模型的三个真实变体，HTTP HEAD 实测）

| 精度 | 文件 | 字节 | 压缩比 |
|---|---|---|---|
| fp32（基线） | `onnx/model.onnx` | 90,387,606 | 1.000× |
| fp16 | `onnx/model_fp16.onnx` | 45,297,825 | **1.996×** |
| q8 / int8 | `onnx/model_quantized.onnx` | 22,972,370 | **3.935×** |

（`Xenova/all-MiniLM-L6-v2`，apache-2.0，384 维，下载量 4.4M）

**这三个变体直接满足 §2.2.3 的「INT8 或 FP16 + 体积/压缩比对比」**，而且是同一模型，不是两个模型对比。

---

## 8. 浏览器与 WebGPU（假设 8 → 部分事实）

| 项 | 实测 |
|---|---|
| 本机浏览器 | **只有 Edge 156.0.4314.50**（`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`）。**没有装 Chrome** |
| `navigator.gpu` | **存在 ✅**（headless=new 下也探测到 `WEBGPU_YES`） |

题面写的是「Chrome / Edge 最新版」，**Edge 156 满足**。但要在 README 里写明「用 Edge 验证；Chrome 未安装，如需 Chrome 请自行安装」。

**未验证**：`navigator.gpu.requestAdapter()` 能否真正拿到适配器并跑出正确向量。`navigator.gpu` 存在 ≠ 有可用适配器（headless 可能是软件后端）。**这一步必须在真实浏览器里跑一次才算数。**

---

## 9. 仍然未验证的 3 条（下一位必须自己确认）

| # | 假设 | 风险 | 怎么验 |
|---|---|---|---|
| 6 | 浏览器里能下载 HF 模型（`huggingface.co` 出网 + 代理） | 中 —— 评审环境也要能下 | 浏览器里跑一次 `pipeline()`，看是否成功加载 |
| 7 | Playwright / Chromium 能装能跑（自动化计时 + Network 取证） | 中 —— 装不动就只能手工计时 | `corepack pnpm dlx playwright install chromium`；本机 `ms-playwright` 目录目前是空的（只有 `.links`） |
| 8b | WebGPU 真能拿到 adapter 并跑出正确向量 | 中 | 浏览器里 `await navigator.gpu.requestAdapter()` |

---

## 10. 给实现者的硬性清单（照着写就不会踩坑）

**依赖（package.json）**

```jsonc
{
  "dependencies": {
    "seekdb": "1.4.0",                       // ← 只能 pnpm 装
    "@huggingface/transformers": "4.3.1"     // 浏览器端推理
  }
  // ❌ 不要 @seekdb/default-embed / qwen / openai / jina（云端 + 装不上）
  // ❌ 不要 @seekdb/bm25（peerDeps 带 workspace:*，装不上）
}
```

**安装命令（写进 README，评审照抄）**

```bash
corepack enable                      # 若失败就跳过，直接用 corepack pnpm
corepack pnpm install --ignore-scripts   # pnpm 12 会拦 build scripts
```

**端侧合规三件套**

1. `VectorIndexConfig({ hnsw:{dimension:384,distance:'cosine'}, embeddingFunction: null })`
2. Node 服务**不装**任何 embedding 依赖，**不加载**任何模型
3. 浏览器算好向量 → `add({ids, documents, embeddings, metadatas})`；查询 → `query/hybridSearch({queryEmbeddings})`

**必须调用 `refresh_index()`**

```js
await collection.add({...});
await collection.refresh_index();     // ← 不调用，向量检索返回空
```

**必须用 `Key` 不是 `K`**

```js
import { Key } from "seekdb";
// sourceKey: Key.DOCUMENT
```

**返回结构**

```js
const ids = result.ids?.[0] ?? [];    // query/hybridSearch 是双层
```

**不要用的 API**：`client.listCollections()`（返回空）、`collection.describe()`（信息太少）。

---

## 11. 本文件所有结论的验证方式

| 结论 | 验证方式 |
|---|---|
| npm 装不上 / pnpm 能装 | `npm.cmd install seekdb`（复现 EUNSUPPORTEDPROTOCOL）、`corepack pnpm add seekdb`（成功） |
| `workspace:*` 的来源 | `npm.cmd pack seekdb@1.4.0` + `npm.cmd pack @seekdb/bm25@1.4.0` 后读 tarball 内 package.json |
| 33 个导出 / 7 个关键导出 | `import * as sdk from "seekdb"` 后 `Object.keys(sdk)` |
| `K !== Key` | 运行时 `typeof` + `K === Key` 比较 |
| Collection 方法列表 | `node_modules/seekdb/dist/index.d.ts` 提取 |
| 混合检索 SQL | `DBMS_HYBRID_SEARCH.GET_SQL()` 手工调用 + 打印生成的 SQL + 执行 |
| RRF 与分数相加两种融合 | `rank.rrf` 有/无各跑一次，对比 SQL 里的 `_score` 表达式 |
| `refresh_index()` 必需 | 刷新前后各跑一次 `query()`，对比返回 |
| 真实表结构 / 索引 | pymysql `show create table` + `show index` |
| 全文索引可用 | pymysql 直跑 `match(document) against(...)` |
| 返回结构双层 vs 单层 | 对比 `query`/`hybridSearch`/`get` 三者输出 |
| dtype / device 选项名 | `@huggingface/transformers/types/**/*.d.ts` |
| 模型体积 | HTTP HEAD 取 content-length |
| Edge WebGPU | Edge `--headless=new --dump-dom` 探测 `navigator.gpu` |
