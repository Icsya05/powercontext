# 端侧知识库 · 浏览器本地向量化 + seekdb 混合检索

> 2026 OceanBase 数据库大赛「阶跃星辰」赛题作品
> 题目：**端侧 AI 推理性能优化与 seekdb 混合检索**

一句话：**把文档拖进浏览器，embedding 在你自己的设备上算完写进 seekdb；提问时同样在本地算查询向量，混合检索由 seekdb 在数据库内完成。**

---

## 1. 作品创意与玩法

一个**完全在浏览器里完成向量化**的个人知识库：

1. **导入** —— 粘贴一段中文文本（露营、烹饪、导航、安全……），浏览器自动切块；
2. **本地向量化** —— 每段文本在你自己的设备上被 embedding 模型编码成 512 维向量，**没有一个字节的原文或向量离开过浏览器去调用云端 API**；
3. **写入 seekdb** —— 向量、原文、元数据一起写进 seekdb 的 `VECTOR(512)` 列，同时建 `ik` 中文全文索引和 VSAG HNSW 向量索引；
4. **提问** —— 查询同样在浏览器本地编码，然后用**一次** `hybridSearch()` 调用同时走「全文腿」和「向量腿」，两腿的融合由 seekdb 数据库内部的 `DBMS_HYBRID_SEARCH` 完成；
5. **看得见的后端** —— 界面顶部永远显示**当前推理后端是 WebGPU 还是 WASM**，降级了会明说。

除了能用，还刻意把「性能」做成了可看的东西：同一个模型可以在 **fp32 / fp16 / q8** 三种精度之间切换，体积、速度、检索质量的差异都有实测数据（见 [TECH_NOTE.md](TECH_NOTE.md)）。

**为什么选中文模型**：题面允许自选开源 embedding 模型。实测下来 `bge-small-zh-v1.5` 的中文召回远好于英文向的 `all-MiniLM-L6-v2`（Recall@10 从 0.385 提到 0.889），所以默认用它。

---

## 2. Dify / seekdb 的分工

| 组件 | 职责 | 证据 |
| --- | --- | --- |
| **浏览器（Transformers.js）** | **全部推理**：文档向量化、查询向量化。WebGPU 优先，不支持自动降级 WASM | `web/src/embedder.ts` |
| **Node 服务（`server/`）** | **纯传输层**：接收浏览器算好的向量 → 调 seekdb → 原样回传结果。零模型、零 embedding 依赖、零自实现排序 | `server/package.json` 只有 `seekdb` 一个依赖 |
| **seekdb** | **存储 + 检索**：向量列 + `ik` 全文索引 + VSAG HNSW；两腿融合（RRF）在数据库内完成 | `DBMS_HYBRID_SEARCH.GET_SQL` |

---

## 3. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Node.js | **>= 20**（实测 v24.16.0） | Transformers.js 与 seekdb-js 都要求 |
| pnpm | 任意（实测 12.16.1） | **必须用 pnpm**，原因见 §5.1 |
| Docker | 任意（实测 Docker Desktop 4.97.0.244584 / Compose v5.6.1） | 用来跑 seekdb |
| seekdb | `oceanbase/seekdb:1.4.0-100000172026082615` | 向量 + 全文检索 |
| 浏览器 | Chrome / Edge 最新版 | 实测 Edge 156；WebGPU 需要 113+ |
| 显卡 | 支持 WebGPU 更好（实测 RTX 5060 / Blackwell） | 没有也能跑，会自动降级 WASM |
| 内存 / 磁盘 | 4 GB 内存、3 GB 磁盘可用 | seekdb 限 4 GB，模型本地副本约 160 MB |

**不需要 Embedding / Rerank 云服务** —— 全部在浏览器本地算。

---

## 4. 从零启动

### 4.1 起 seekdb

```bash
docker run -d --name stepfun-seekdb \
  -e ROOT_PASSWORD=StepFun@2026 \
  -p 28811:2881 -p 28816:2886 \
  -v stepfun-seekdb-data:/var/lib/seekdb \
  --restart unless-stopped \
  oceanbase/seekdb:1.4.0-100000172026082615
```

等它 healthy（约 40 秒），然后建库：

```bash
docker exec stepfun-seekdb mysql -uroot -pStepFun@2026 -h 127.0.0.1 -P 2881 \
  -e "CREATE DATABASE IF NOT EXISTS stepfun_kb DEFAULT CHARACTER SET utf8mb4;"
```

> **Windows 必须用命名卷**（`-v stepfun-seekdb-data:/var/lib/seekdb`），不要用宿主目录 bind mount。
> 端口 28811/28816 是为了避开别的 seekdb 实例；可以随意改，改了同步改 `stepfun/.env`。

### 4.2 装依赖

```bash
cd stepfun
node scripts/setup.mjs          # 等价于在 server/ 和 web/ 里各跑一次 pnpm install --ignore-scripts
```

### 4.3 预置模型（让浏览器不必联网）

```bash
node scripts/fetch-model.mjs    # 下载 fp32 / fp16 / q8 三个 ONNX 变体到 web/public/models/
```

这一步下载约 160 MB。**做完之后浏览器完全不需要访问 huggingface.co** —— 模型从本地 `/models/` 加载，评测环境无外网也能跑。
下载走 `HTTPS_PROXY` 环境变量（如果你的网络需要代理）。

### 4.4 构建前端

```bash
node scripts/build-web.mjs     # 复制 wasm 与语料 -> vite build -> web/dist
```

### 4.5 起服务

```bash
# 配置（可选，不配就用默认值）
cp .env.example .env            # Windows: copy .env.example .env
# 按需改 SEEKDB_PASSWORD / SEEKDB_PORT / SEEKDB_DIMENSION

node server/start.mjs
```

打开 **http://127.0.0.1:8080**。

> 服务端会读同目录的 `.env`（`stepfun/.env`）。**这个文件已在 `.gitignore` 里，不要提交。**

### 4.6 一条命令跑完全部自检

```bash
node scripts/check_compliance.mjs   # 端侧合规静态自检（104 项）
node scripts/check_api.mjs          # 服务端 API 端到端检查（29 项）
```

---

## 5. 关键实现细节（踩过的坑都在这）

### 5.1 为什么必须用 pnpm

`seekdb@1.4.0` 的**发布包**里 `workspace:` 协议没被重写，npm 装的时候会直接失败：

```
npm error code EUNSUPPORTEDPROTOCOL
npm error Unsupported URL Type "workspace:": workspace:*
```

`--omit=optional` 也救不了。用 pnpm 就没有问题：

```bash
corepack pnpm install --ignore-scripts
```

`--ignore-scripts` 是因为 pnpm 12 默认拦截依赖的构建脚本，而浏览器端不需要 `onnxruntime-node` 的原生构建。

> 同理 `@seekdb/bm25` 也装不上（它的 `peerDependencies` 里也是 `workspace:*`），所以**本作品没有 BM25 第三路稀疏检索**，只用「稠密向量 + ik 全文」两路。

### 5.2 `refresh_index()` 不调用，向量检索返回空

seekdb 的向量索引是 `SYNC_MODE=ASYNC`。`collection.add()` 之后**必须**刷新：

```js
await collection.add({ ids, documents, embeddings, metadatas });
await collection.refresh_index();   // 不调用 -> query() 返回空数组
```

实测 64 条文档的刷新耗时约 500–700 ms，这是 §3.2 要求单独统计的「写入与索引刷新」阶段。

### 5.3 `getCollection` 必须显式传 `embeddingFunction: null`

服务端**没有也不该有** embedding 函数。但 SDK 的 `getCollection()` 在不传这个参数时，会去加载「默认」embedding 函数（`@seekdb/default-embed`），而那个包因为 `workspace:` 协议根本装不上 → 直接抛
`Embedding function 'default-embed' is not registered`。

```js
collection = await client.getCollection({
  name: "kb",
  embeddingFunction: null,   // ← 关键
});
```

同理，建集合时 `VectorIndexConfig({ ..., embeddingFunction: null })`。

### 5.4 混合检索的返回结构是双层嵌套

`query()` / `hybridSearch()` 返回的是 `ids: [["a","b","c"]]`（外层是查询组，内层才是结果），而 `get({ids})` 返回的是单层 `["a","b"]`。前端要按 `result.ids?.[0]` 取。

> 坑：用 `String(result.documents[0])` 打印会「看起来正常」，因为数组转字符串会自动 join，很容易误判成单层。**用 `Array.isArray(result.ids[0])` 判断。**

### 5.5 `whereDocument` 只作用于全文腿

`hybridSearch` 生成的 SQL 是两腿 `FULL JOIN`，所以最终结果是**两腿的并集** —— 搜「账本」也会返回不含「账本」但向量上相近的文档。这不是 bug，是 RRF 融合的设计。

### 5.6 seekdb-js 的 `deleteCollection()` 有 bug

它只删物理表，**不删 `sdk_collections` 里的元数据行**，之后 `createCollection()` 会报
`Duplicate entry 'kb' for key 'idx_name'`。所以本作品的「清空知识库」是**删数据行**而不是删集合，避开这个坑；服务端启动时还会自动清理「元数据在、表没了」的残留状态。

### 5.7 WebGPU 探测要看 adapter，不能只看 `navigator.gpu`

```js
const adapter = await navigator.gpu.requestAdapter();
if (!adapter) { /* 降级 WASM */ }
```

另外：给浏览器加 `--use-angle=swiftshader` 会强制软件渲染，让 `requestAdapter()` 返回 null，**WebGPU 路径根本走不到** —— 调试时别加这个参数。

还有一点：**WebGPU 要求安全上下文**，`about:blank` 不是安全上下文（`navigator.gpu` 直接是 undefined），要在 `http://127.0.0.1` 或 `https://` 下测。

---

## 6. 混合检索如何由 seekdb 完成

SDK 并**不是**在客户端拼两路结果。它把参数交给 seekdb 内部的存储过程，由数据库生成并执行融合 SQL：

```sql
SET @search_parm = '{"query":{"query_string":{"fields":["document"],"query":"账本"}},
                     "knn":{"field":"embedding","k":30,"query_vector":[...]},
                     "rank":{"rrf":{"rank_window_size":60,"rank_constant":60}},
                     "size":10}';

SELECT DBMS_HYBRID_SEARCH.GET_SQL('c$v2$xxx', @search_parm) as query_sql FROM dual;
```

seekdb 返回的 SQL（节选自实测）：

```sql
SELECT ifnull(_fts._id, _vs._id) as _id, ...,
       (ifnull(_fts._keyword_score, 0) + ifnull(_vs._semantic_score, 0)) as _score
FROM (
  -- 全文腿
  SELECT ..., match(`document`) against('账本' in natural language mode) as _keyword_score
  FROM `stepfun_kb`.`c$v2$xxx`
  WHERE match(`document`) against('账本' in natural language mode)
  ORDER BY _keyword_score DESC LIMIT 60
) `_fts`
FULL JOIN (
  -- 向量腿
  SELECT ..., round(1 - cosine_distance(`embedding`, '[...]') / 2, 8) as _semantic_score
  FROM `stepfun_kb`.`c$v2$xxx`
  ORDER BY cosine_distance(`embedding`, '[...]') APPROXIMATE LIMIT 30
) `_vs`
ON `_fts`.`__pk_increment` = `_vs`.`__pk_increment`
ORDER BY _score DESC, ifnull(_vs.__pk_increment, _fts.__pk_increment) LIMIT 10
```

传 `rank: { rrf: {...} }` 时融合换成 RRF：`1/(rank+60) + 1/(rank+60)`。**两腿的融合在数据库里完成，前端只发一次请求、只收一次结果。**

---

## 7. 表结构与索引

```sql
CREATE TABLE `c$v2$<collection_id>` (
  `_id`        varbinary(512) NOT NULL,
  `document`   string DEFAULT NULL,
  `embedding`  VECTOR(512) DEFAULT NULL,
  `metadata`   json DEFAULT NULL,
  PRIMARY KEY (`_id`),
  FULLTEXT KEY `idx_fts` (`document`)
      WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart") BLOCK_SIZE 16384,
  VECTOR KEY `idx_vec` (`embedding`)
      WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, M=16, EF_CONSTRUCTION=200,
            EF_SEARCH=64, SYNC_MODE=ASYNC) BLOCK_SIZE 16384
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4;

CREATE TABLE `sdk_collections` (     -- SDK 自己的集合登记表
  `collection_id`   char(32) NOT NULL DEFAULT (replace(uuid(),'-','')),
  `collection_name` string DEFAULT NULL,
  `settings`        json DEFAULT NULL COMMENT 'Generated by SDK, don\'t modify',
  `created_at`      timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`collection_id`),
  UNIQUE KEY `idx_name` (`collection_name`) BLOCK_SIZE 16384 LOCAL
) ORGANIZATION INDEX DEFAULT CHARSET = utf8mb4;
```

页面上的「查看 seekdb 表结构」按钮会实时读出上面这些内容；「导出行级数据」会直接 SELECT 出原文与元数据。

---

## 8. 验证样例

完整的验证样例（初始状态、输入、操作顺序、预期表现、恢复初始状态）见 **[docs/WALKTHROUGH.md](docs/WALKTHROUGH.md)**。

实测证据（真实运行产出）：

| 文件 | 内容 |
| --- | --- |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) | 逐条对照官方 §3.1 七项验收的证据 |
| [bench/results/quality.md](bench/results/quality.md) | Recall@K / nDCG@K 与分阶段耗时 |
| [bench/results/quality.json](bench/results/quality.json) | 同上的机器可读版本 |
| `bench/raw/bench-raw-*.json` | 浏览器自动化的原始记录（含每一次请求、耗时、后端） |

一键复现：

```bash
cd bench
corepack pnpm install --ignore-scripts   # 装 Playwright（用系统浏览器，不额外下载 Chromium）
node run.mjs                               # WebGPU 路径
node run.mjs --wasm                        # 强制降级到 WASM 的对照
node score.mjs raw/bench-raw-*.json        # 合并打分
```

---

## 9. 已知限制

- **本机没有装 Chrome**，实测用的是 Edge 156。题面写的是「Chrome / Edge 最新版」，Edge 满足。
- **WASM 后端下 fp16 与 fp32 结果完全一致**：onnxruntime-web 的 WASM 内核不支持 fp16 计算，会自动上转；fp16 的体积优势（1.997×）要到 WebGPU 后端才兑现。
- **q8 量化在 WebGPU 上比 fp32 慢**（向量化 1173 ms vs 510 ms）：反量化开销在 GPU 上没有摊薄。q8 的价值是体积（3.95×）和 WASM 上的速度。
- **未使用 BM25 稀疏检索**（`@seekdb/bm25` 因 `workspace:` 协议装不上），题面未要求第三路。
- **模型文件不入库**：约 160 MB，用 `scripts/fetch-model.mjs` 一次性下载到本地。
- **浏览器缓存**：模型走 Cache Storage，第二次加载会快很多，但首次仍需下载。
- **ONNX Runtime 的 WASM 是单线程**（`numThreads = 1`），避免要求 COOP/COEP 跨源隔离。

---

## 10. 来源与许可

| 资源 | 来源 | 许可 |
| --- | --- | --- |
| embedding 模型 | [Xenova/bge-small-zh-v1.5](https://huggingface.co/Xenova/bge-small-zh-v1.5)（原模型 BAAI/bge-small-zh-v1.5） | apache-2.0 |
| 端侧运行时 | [@huggingface/transformers](https://www.npmjs.com/package/@huggingface/transformers) 4.3.1 | Apache-2.0 |
| ONNX Runtime Web | [onnxruntime-web](https://www.npmjs.com/package/onnxruntime-web) | MIT |
| 数据库 SDK | [seekdb](https://www.npmjs.com/package/seekdb) 1.4.0（源码 [oceanbase/seekdb-js](https://github.com/oceanbase/seekdb-js)） | Apache-2.0 |
| 数据库 | [oceanbase/seekdb](https://github.com/oceanbase/seekdb) 镜像 `1.4.0-100000172026082615` | Apache-2.0 |
| 构建 | [Vite](https://vite.dev/) 7.x | MIT |
| 自动化 | [Playwright](https://playwright.dev/) 1.x | Apache-2.0 |

代码改动均为本作品原创，未复制任何第三方作品源码。
