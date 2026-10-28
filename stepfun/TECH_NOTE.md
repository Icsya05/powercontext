# 一页技术说明

> 作品：端侧知识库（浏览器本地向量化 + seekdb 混合检索）
> 赛题：2026 OceanBase 数据库大赛 · 阶跃星辰 · 端侧 AI 推理性能优化与 seekdb 混合检索
> 实测环境：Windows 11 x64 / Node v24.16.0 / Edge 156.0.4314.50 / NVIDIA RTX 5060 Laptop GPU (Blackwell)
> 所有数字均来自 `bench/raw/` 里浏览器自动化的原始记录，可用 §5 的命令复现。

---

## 1. 模型与量化

| 项 | 内容 |
| --- | --- |
| 模型 | `Xenova/bge-small-zh-v1.5`（原模型 BAAI/bge-small-zh-v1.5，**apache-2.0**，公开可获取） |
| 选择理由 | 题面允许自选开源 embedding 模型。实测该模型中文召回显著优于英文向的 `all-MiniLM-L6-v2`：Recall@10 **0.889 vs 0.385** |
| 运行时 | `@huggingface/transformers` 4.3.1（Transformers.js，浏览器内） |
| 池化 / 归一化 | BGE 官方推荐 **CLS pooling** + L2 归一化，输出 **512 维** |
| 量化方案 | 同一模型的三个官方 ONNX 变体：`onnx/model.onnx`(fp32)、`onnx/model_fp16.onnx`(fp16)、`onnx/model_quantized.onnx`(q8/int8) |

**量化前后体积与压缩比**（同一口径：模型权重文件实际字节数，由 `scripts/fetch-model.mjs` 下载后实测）

| 精度 | 文件 | 体积(B) | 压缩比 |
| --- | --- | --- | --- |
| fp32（基线） | `onnx/model.onnx` | 94,851,877 | 1.000× |
| fp16 | `onnx/model_fp16.onnx` | 47,497,427 | **1.997×** |
| q8 / int8 | `onnx/model_quantized.onnx` | 24,010,842 | **3.950×** |

**检索质量变化**（同一评测集：64 篇中文文档 + 24 条带人工相关性标注的查询；详见 `bench/results/quality.md`）

| 配置 | Recall@1 | nDCG@1 | Recall@5 | nDCG@5 | Recall@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| fp32 + WebGPU（基线） | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| fp16 + WebGPU | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| q8 + WebGPU | 0.4722 | 0.8333 | **0.7778** | **0.8014** | 0.8785 | 0.8346 |
| fp32 + WASM | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| fp16 + WASM | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| q8 + WASM | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8785 | 0.8333 |

> 结论：**fp16 在本评测集上与 fp32 质量完全一致，体积减半；q8 体积降到 1/3.95，Recall@10 只掉 1.04 个百分点。** 量化没有明显损害检索质量。
> 评测方法：Recall@K = 前 K 条命中的相关文档数 / 全部相关文档数；nDCG@K 用 graded relevance（2=直接相关，1=部分相关），DCG = Σ gain/log₂(rank+1)，IDCG 按相关性降序取前 K 条。相关性标注是**逐条人工写死**的，不是按主题自动生成的。

---

## 2. 端侧运行

| 项 | 内容 |
| --- | --- |
| 运行时 | Transformers.js（`@huggingface/transformers` 4.3.1），底层 onnxruntime-web |
| WebGPU 选择 | `pipeline(..., { device: "webgpu" })` **显式指定**；启动前先 `await navigator.gpu.requestAdapter()` 探测 |
| 自动降级 | `requestAdapter()` 返回 null 或抛错 → 换 `device: "wasm"` 重载，**界面顶部横幅明示当前后端与降级原因**；另提供「强制降级到 WASM」开关供评审一键验证 |
| 推理位置 | 文档向量化与查询向量化**全部在浏览器内**。浏览器把算好的向量 POST 给服务端，服务端只转发 |
| 无云端推理 | 基准脚本记录了浏览器发出的**全部网络请求：外部请求数 = 0**（`bench/raw/*.json` 的 `externalRequests` 字段） |

**实测后端与耗时**（64 篇文档，24 条查询）

| 配置 | 模型加载(ms) | 文档向量化(ms) | 查询向量化中位数(ms) |
| --- | --- | --- | --- |
| fp32 + WebGPU | 1315 | **510** | 6.55 |
| fp16 + WebGPU | 285 | **322** | 6.60 |
| q8 + WebGPU | 178 | 1173 | 68.90 |
| fp32 + WASM | 1138 | 1746 | 10.00 |
| fp16 + WASM | 337 | 1747 | 10.70 |
| q8 + WASM | 158 | **857** | 6.65 |

> 降级路径验证结果：同一套代码在 WebGPU 与 WASM 下**检索质量完全一致**（上表六行的 Recall/nDCG 逐项相同），说明降级只影响速度、不影响正确性。
> 实测适配器：`vendor=nvidia, architecture=blackwell`。

---

## 3. seekdb 使用

| 项 | 内容 |
| --- | --- |
| 接入方式 | **seekdb-js**（npm `seekdb@1.4.0`，服务端模式，MySQL 协议 2881） |
| 表结构 | 每集合一张表 `c$v2$<collection_id>`：`_id varbinary(512)` / `document string` / `embedding VECTOR(512)` / `metadata json` |
| 索引 | `idx_fts`：`FULLTEXT … WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart")`；`idx_vec`：`VECTOR KEY … DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, M=16, EF_CONSTRUCTION=200, EF_SEARCH=64, SYNC_MODE=ASYNC` |
| 混合检索 | `collection.hybridSearch({ query, knn, rank: { rrf: { rankWindowSize: 60, rankConstant: 60 } }, nResults })` |
| 融合位置 | **数据库内**。SDK 先 `SET @search_parm`，再调 `DBMS_HYBRID_SEARCH.GET_SQL(table, @search_parm)` 生成 `FULL JOIN` 两腿（全文腿 `match(document) against(... in natural language mode)`，向量腿 `cosine_distance(...)`）的 SQL 并执行。前端只发一次请求、只收一次结果 |
| 增量写入 | `collection.add({ ids, documents, embeddings, metadatas })` → **必须** `collection.refresh_index()`（索引是 `SYNC_MODE=ASYNC`），实测 64 条刷新约 500–700 ms |
| 集合/会话状态 | 集合级状态由 `sdk_collections` 表持久化；页面每次操作都从服务端读当前集合状态；「清空知识库」= 删数据行（保留表结构与索引），保证回到**可复现的初始状态** |
| 服务端职责 | `server/package.json` 的运行时依赖**只有 `seekdb` 一个**；`scripts/check_compliance.mjs` 用 104 项静态检查证明服务端不 import 任何模型包、不含任何云端推理域名、没有自实现的排序函数 |

---

## 4. 状态与优化

**状态管理**
- 集合状态：`sdk_collections` 表持久化，服务端重启后用 `getCollection({ name, embeddingFunction: null })` 恢复（必须显式传 `null`，否则 SDK 会去加载装不上的默认 embedding 函数）。
- 索引状态：写入后显式刷新；服务端启动时自动清理「元数据在、物理表没了」的残留（seekdb-js 的 `deleteCollection()` 只删表不删元数据，是已知缺陷）。
- 会话状态：浏览器侧无状态，集合与知识库状态以 seekdb 为准；界面每次操作都读服务端当前状态。

**优化点与实测收益**

| 优化 | 做法 | 实测收益 |
| --- | --- | --- |
| 批量向量化 | batch size 16，一次 `pipeline()` 批量 encode，避免逐条调度 | 64 篇文档 **510 ms**（WebGPU fp32） |
| 模型本地化 | `scripts/fetch-model.mjs` 把三个精度变体预置到 `/models/`，浏览器不再访问外网 | 外部请求数 **0**，离线可跑 |
| wasm 运行时本地化 | onnxruntime-web 的 wasm 复制到 `/ort/`，不依赖 CDN | 同上 |
| 后端自适应 | 探测不到 WebGPU 才降级，且降级后质量完全一致 | 降级路径实测可用 |
| 单线程 WASM | `numThreads = 1`，不要求 COOP/COEP 跨源隔离 | 评审用普通方式起服务即可跑 |
| RRF 融合 | 两腿分数量纲不同（全文分 ~0.3、向量分 ~0.5），改用 RRF 而不是直接相加 | 排序更稳 |
| 量化换体积 | q8 变体体积降到 1/3.95，Recall@10 仅 -1.04 个百分点 | 体积换质量可控 |

**未采纳 / 已知不足**
- BM25 稀疏第三路：`@seekdb/bm25` 的发布包 `peerDependencies` 带 `workspace:*`，npm 与 pnpm 都装不上，故改用两路。
- q8 在 WebGPU 上比 fp32 慢（1173 ms vs 510 ms）：反量化开销在 GPU 上没有摊薄，q8 的价值在体积与 WASM 场景。
- fp16 在 WASM 下与 fp32 结果完全相同：onnxruntime-web 的 WASM 内核不支持 fp16 计算，会自动上转。

---

## 5. 复现方式

```bash
# 1) 起 seekdb（见 README §4.1）
# 2) 装依赖 + 预置模型 + 构建前端
cd stepfun
node scripts/setup.mjs && node scripts/fetch-model.mjs && node scripts/build-web.mjs

# 3) 起服务
node server/start.mjs

# 4) 跑基准（WebGPU 路径 / 强制 WASM 对照）
cd bench
corepack pnpm install --ignore-scripts
node run.mjs
node run.mjs --wasm
node score.mjs raw/bench-raw-*.json

# 5) 自检
cd ..
node scripts/check_compliance.mjs
node scripts/check_api.mjs
```
