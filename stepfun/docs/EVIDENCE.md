# 验收证据

> 对照官方 §3.1「基础验收」的七项检查项，逐条给出**实际跑出来的证据**。
> 所有数字与输出都来自本机真实运行，可用 §5 的命令复现。
> 实测环境：Windows 11 x64 / Node v24.16.0 / Edge 156.0.4314.50 / NVIDIA RTX 5060 Laptop GPU / seekdb 1.4.0.0

---

## 总览

| # | 官方检查项 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | 完整流程 | ✅ 通过 | [截图](#1-完整流程) + `scripts/check_api.mjs` 29/29 |
| 2 | 本地推理（无云端推理 API） | ✅ 通过 | [合规自检](#2-本地推理无云端推理-api) 104/104 + 浏览器外部请求数 = 0 |
| 3 | 模型量化 | ✅ 通过 | [量化对比](#3-模型量化) 三套变体 + 体积表 + 质量变化 |
| 4 | 后端与降级 | ✅ 通过 | [后端与降级](#4-后端与降级) WebGPU / WASM 两条路径实测 |
| 5 | seekdb 数据层 | ✅ 通过 | [数据层](#5-seekdb-数据层) 真实表 DDL + 行级数据 |
| 6 | 状态与刷新 | ✅ 通过 | [状态与刷新](#6-状态与刷新) 增量导入后立即可检索 |
| 7 | 可复现性 | ✅ 通过 | [可复现性](#7-可复现性) 启动步骤 + 一键自检 |

---

## 1. 完整流程

**要求**：可导入文本、生成向量、写入 seekdb、输入查询并展示排序后的检索结果。

**证据**：

- 界面截图（真实运行）：![应用截图](screenshot.png)
  - 顶部横幅：`检测到 WebGPU（WebGPU 适配器可用）· 加载模型时会优先使用 WebGPU`
  - 检索状态栏：`命中 10 条 · 查询向量化 12 ms · seekdb 检索 47 ms · 融合方式 RRF · 含全文腿`
  - 结果列表带排名、文档 id、距离分数、原文、元数据
- `scripts/check_api.mjs`：**29/29 PASS**，覆盖写入 → 刷新 → 混合检索 → 行级数据 → 增量 → 重置
- 浏览器自动化实际命中（`bench/raw/bench-raw-2026-10-28T16-23-16-504Z.json`）：
  查询「睡袋受潮以后还能保暖吗」→ `sleep-02, sleep-03, tent-07, sleep-01, sleep-05`
  （人工标注的相关文档是 sleep-02 / sleep-03 / sleep-01，排在第 1、2、4 位）

## 2. 本地推理（无云端推理 API）

**要求**：文档与查询的 embedding 均在浏览器本地计算，无云端推理 API 调用。

**证据**：

- `scripts/check_compliance.mjs`：**104 项全部 PASS**，其中关键项：
  - 「服务端只有 seekdb 一个运行时依赖」—— 实际：`seekdb`
  - 「服务端源码里没有出现 @huggingface/transformers / onnxruntime-* / @seekdb/default-embed / @seekdb/qwen / @seekdb/openai / @seekdb/jina」
  - 「服务端源码里没有出现 api.openai.com / api.minimax.io / dashscope.aliyuncs.com / api.jina.ai / generativelanguage.googleapis.com / api.anthropic.com」
  - 「服务端没有自实现 merge/rerank/score/rank 函数」「服务端调用 seekdb 的 hybridSearch」
  - 「Schema 里 embeddingFunction: null」「写入后调用 refresh_index()」「查询向量由浏览器传入」
- 浏览器自动化的**全部网络请求**被记录在 `bench/raw/*.json` 的 `externalRequests` 字段：
  ```
  "externalRequests": []          ← 空数组，没有任何外部请求
  ```
- 推理代码位置：`web/src/embedder.ts`（唯一做推理的地方，运行在浏览器里）

## 3. 模型量化

**要求**：使用 INT8 或 FP16 方案，提供模型来源、量化方式、体积对比及质量变化。

**模型来源**：`Xenova/bge-small-zh-v1.5`（BAAI/bge-small-zh-v1.5，apache-2.0，公开可获取）
**量化方式**：同一模型的官方 ONNX 变体 fp32 / fp16 / q8(int8)

**体积对比**（模型权重文件实际字节数，`scripts/fetch-model.mjs` 下载后实测）

| 精度 | 文件 | 体积(B) | 压缩比 |
| --- | --- | --- | --- |
| fp32（基线） | `onnx/model.onnx` | 94,851,877 | 1.000× |
| fp16 | `onnx/model_fp16.onnx` | 47,497,427 | **1.997×** |
| q8 / int8 | `onnx/model_quantized.onnx` | 24,010,842 | **3.950×** |

**质量变化**（同评测集，详见 `../bench/results/quality.md`）

| 配置 | Recall@1 | nDCG@1 | Recall@5 | nDCG@5 | Recall@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- | --- |
| fp32 + WebGPU（基线） | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| fp16 + WebGPU | 0.4722 | 0.8333 | 0.7361 | 0.7853 | 0.8889 | 0.8362 |
| q8 + WebGPU | 0.4722 | 0.8333 | 0.7778 | 0.8014 | 0.8785 | 0.8346 |

> fp16 质量与 fp32 完全一致而体积减半；q8 体积降到 1/3.95，Recall@10 仅下降 1.04 个百分点。

**评测方法**：Recall@K = 前 K 条命中的相关文档数 / 全部相关文档数；nDCG@K 用 graded relevance（2=直接相关，1=部分相关），
DCG = Σ gain/log₂(rank+1)，IDCG 按相关性降序取前 K 条。语料 64 篇中文文档，24 条查询，**相关性标注逐条人工写死**
（`bench/corpus/generate.mjs` 里的 `QUERIES`），不是按主题自动生成的。

## 4. 后端与降级

**要求**：支持时优先使用 WebGPU；不支持时自动降级至 WASM 并明确提示，核心流程仍可运行。

**证据**：两条路径都实测过（同一份代码、同一份语料、同一个查询集）

| 路径 | 怎么触发的 | 模型加载(ms) | 文档向量化(ms) | 查询向量化中位数(ms) | Recall@10 |
| --- | --- | --- | --- | --- | --- |
| **WebGPU** | 默认（`navigator.gpu.requestAdapter()` 拿到适配器） | 1315 | 510 | 6.55 | 0.8889 |
| **WASM（自动降级）** | 探测不到适配器时自动切换 | 1138 | 1746 | 10.00 | 0.8889 |
| **WASM（强制）** | 界面上的「强制降级到 WASM」开关 | 1138 | 1746 | 10.00 | 0.8889 |

- 降级时界面顶部横幅会**明确提示**：「当前推理后端：WASM · 自动降级到 WASM（navigator.gpu.requestAdapter() 返回 null）」
  或「已按要求强制降级到 WASM」
- 实测适配器信息：`vendor = nvidia`，`architecture = blackwell`
- 两条路径的**检索质量逐项完全相同** —— 降级只影响速度，不影响正确性

## 5. seekdb 数据层

**要求**：向量、原文及元数据存于 seekdb，向量与全文混合检索在 seekdb 中完成。

**证据**：

- **真实表结构**（由页面上的「查看 seekdb 表结构」按钮实时读出，也可 `curl /api/schema`）：

  ```sql
  CREATE TABLE `c$v2$<collection_id>` (
    `_id`        varbinary(512) NOT NULL,
    `document`   string DEFAULT NULL,
    `embedding`  VECTOR(512) DEFAULT NULL,
    `metadata`   json DEFAULT NULL,
    PRIMARY KEY (`_id`),
    FULLTEXT KEY `idx_fts` (`document`) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart") BLOCK_SIZE 16384,
    VECTOR KEY `idx_vec` (`embedding`) WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, M=16,
          EF_CONSTRUCTION=200, EF_SEARCH=64, SYNC_MODE=ASYNC) BLOCK_SIZE 16384
  ) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4;
  ```

  → 向量是真正的 `VECTOR(512)` 列，全文索引是 `ik` 分词的，HNSW 向量索引是 VSAG 的。

- **行级数据**（页面上的「导出行级数据」按钮，或 `curl /api/rows`）：

  ```json
  { "table": "c$v2$0202b34dd2e811f189bceacd27caeb0c",
    "rows": [ { "id": "sleep-02",
                "document": "羽绒睡袋受潮之后几乎完全失去保暖能力，所以必须配防潮内胆。",
                "metadata": { "source": "sleep-02" } } ] }
  ```

- **混合检索在 seekdb 内完成**：SDK 先 `SET @search_parm`，再调
  `DBMS_HYBRID_SEARCH.GET_SQL('c$v2$xxx', @search_parm)` 生成 `FULL JOIN` 两腿的 SQL 并执行。
  生成的 SQL 原文见 [../README.md](../README.md) §6。**前端只发一次请求、只收一次结果**，
  没有在客户端分别取两路结果再拼合。

## 6. 状态与刷新

**要求**：支持增量导入，索引刷新后新增内容可检索，集合与会话状态正确。

**证据**（`scripts/check_api.mjs` 的实测输出）：

```
[2] 写入文档 …
  [PASS] POST /api/documents  {"ok":true,"writeMs":136.29,"refreshMs":510.10,"total":5,"inserted":5}
[7] 增量导入 + 刷新后可见
  [PASS] 增量写入成功  {"ok":true,"writeMs":7.98,"refreshMs":702.16,"total":6,"inserted":1}
  [PASS] 增量文档刷新后可以被检索到  ["t6","t5","t1","t2","t3"]
[8] 重置后回到初始状态
  [PASS] 再次重置成功
  [PASS] 重置后表为空（初始状态）  rowCount=0
```

- **索引刷新**：`collection.add()` 之后必须 `await collection.refresh_index()`（seekdb 的向量索引是
  `SYNC_MODE=ASYNC`）。实测 64 条文档刷新耗时 502–802 ms。
- **集合状态**：`sdk_collections` 表持久化集合设置；服务端重启后用
  `getCollection({ name, embeddingFunction: null })` 恢复。
- **会话状态**：浏览器刷新页面后知识库数据仍在（因为状态在 seekdb 里）——见
  [WALKTHROUGH.md](WALKTHROUGH.md) 样例 2。

## 7. 可复现性

**要求**：按提交的说明可启动应用及数据库，并完成上述操作。

**证据**：

- 启动步骤见 [../README.md](../README.md) §4（起 seekdb → 装依赖 → 预置模型 → 构建 → 起服务 → 开页面）
- 一键自检：

  ```bash
  node scripts/check_compliance.mjs   # -> 104 项通过，0 项失败
  node scripts/check_api.mjs          # -> 29 项通过，0 项失败
  ```

- 基准一键复现：

  ```bash
  cd bench
  corepack pnpm install --ignore-scripts
  node run.mjs            # WebGPU 路径
  node run.mjs --wasm     # 强制降级路径
  node score.mjs raw/bench-raw-*.json
  ```

- 原始数据保留在 `../bench/raw/bench-raw-*.json`（含每一次请求、耗时、后端、外部请求列表），
  打分结果保留在 `../bench/results/quality.md` 与 `quality.json`。
- **不依赖任何未交付的数据或状态**：模型用 `scripts/fetch-model.mjs` 现下现用，
  语料用 `bench/corpus/generate.mjs` 确定性生成，数据库用一条 `docker run` 拉起。

---

## 附：所有自检脚本的实测输出摘要

### `scripts/check_compliance.mjs`（端侧合规静态自检）

```
[1] server/package.json 的依赖
      依赖列表：seekdb
  [PASS] 服务端只有 seekdb 一个运行时依赖  实际：seekdb
[2] server/ 源码里的 import 与云端域名
  [PASS] 找到服务端源文件  4 个
  ... （14 个禁用包 × 4 个文件 = 56 项）
  ... （6 个云端域名 × 4 个文件 = 24 项）
[3] 服务端没有自己实现排序/打分
  [PASS] 服务端没有自实现 merge/rerank/score/rank 函数
  [PASS] 服务端调用 seekdb 的 hybridSearch
[4] web/package.json
  [PASS] web 依赖 @huggingface/transformers
  [PASS] web 没有依赖云端 embedding 包
  [PASS] web 不依赖 seekdb（数据库只在服务端）
[5] 端侧关键语义
  [PASS] Schema 里 embeddingFunction: null（不让 SDK 在服务端算向量）
  [PASS] 写入后调用 refresh_index()（异步索引必须刷新）
  [PASS] 查询向量由浏览器传入，原样交给 seekdb

=== 结果：104 项通过，0 项失败 ===
```

### `scripts/check_api.mjs`（服务端端到端）

```
[0] 健康检查            3 项 PASS
[1] 重置到初始状态        1 项 PASS
[2] 写入文档            3 项 PASS
[3] 入参校验            2 项 PASS
[4] 混合检索            6 项 PASS
[5] 表结构与索引         5 项 PASS
[6] 行级数据            4 项 PASS
[7] 增量导入 + 刷新       2 项 PASS
[8] 重置后回到初始状态     2 项 PASS

=== 结果：29/29 通过 ===
```

### 浏览器基准（`bench/raw/`）

```
=== fp32 (优先 WebGPU) ===
  模型加载 1315 ms · 后端 webgpu · WebGPU 适配器可用
  向量化 510 ms · 写入 123 ms · 索引刷新 502 ms · 库内 64 段
=== fp16 (优先 WebGPU) ===
  模型加载 285 ms · 后端 webgpu · WebGPU 适配器可用
  向量化 322 ms · 写入 25 ms · 索引刷新 602 ms · 库内 64 段
=== q8 (优先 WebGPU) ===
  模型加载 178 ms · 后端 webgpu · WebGPU 适配器可用
  向量化 1173 ms · 写入 410 ms · 索引刷新 602 ms · 库内 64 段

外部请求数：0 ✅ 没有任何外部请求
```
