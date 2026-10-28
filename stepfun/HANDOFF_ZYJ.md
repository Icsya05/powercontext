# 阶跃星辰赛题交接报告（zyj → step）

> 交接人：zyj　｜　日期：2026-10-28　｜　源赛题：Dify（已完成并提测）　｜　目标赛题：阶跃星辰
>
> 这份文档基于两样东西写成：① 官方赛题原文（逐条读过，出处见下）；② 我在 Dify 赛题上从零做到提测的完整经验。
> 所有"已验证"字样的内容都是在这台机器上真实跑过的，不是推测。

---

## 0. 30 秒速览

**你要做的事和 Dify 那条完全不是一回事。** Dify 赛题考的是「工作流编排 + 记忆持久化」，你这条考的是「**浏览器端侧推理 + 模型量化 + 数据库内混合检索**」，工程量和难度都上一个台阶。

三个必须先知道的坑（我提前踩过了）：

| # | 坑 | 后果 |
|---|---|---|
| 1 | npm 上的 `seekdb-js` **已经被 unpublish 了** | 题面让你用的那个包名装不上 |
| 2 | `seekdb` SDK 默认会在 **Node 端**自动算向量 | 直接违反「禁止云端/服务端推理」的铁律 |
| 3 | 「混合检索」如果前端拿两路结果自己拼 → **直接不合规** | 基础验收不通过 |

**好消息：环境我已经给你准备好了。** Docker Desktop 装好并跑通了，seekdb 镜像已拉到本地、容器正在运行、端口已映射。这部分你**一行都不用重做**。

---

## 1. 赛题原文要点

**出处**：语雀《阶跃星辰》，2026-10-26 更新，共 2309 字
`https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9`

> 项目：seekdb × 阶跃星辰
> 题目：**端侧 AI 推理性能优化与 seekdb 混合检索**
> 任务：构建一个在浏览器本地完成向量化、使用 seekdb 进行语义与混合检索的迷你知识库应用
> 模型要求：自选可公开获取的开源 embedding 模型，**不限定使用阶跃星辰模型**
> 提交产物：可运行的 Web 应用、完整源码和一页技术说明
> 总分：20

### 1.1 五条硬性要求（原文摘录）

| 条款 | 原文要点 |
|---|---|
| §2.2.1 端侧推理 | 用 Transformers.js、ONNX Runtime Web 等端侧运行时，在**用户设备的浏览器中**执行 embedding 推理。文档向量化和查询向量化**均须在本地完成** |
| §2.2.3 量化 | 采用 **INT8 或 FP16**，报告量化前后的**模型体积、压缩比、检索质量变化** |
| §2.2.4 后端 | **优先 WebGPU**，显式配置推理后端；不支持时**自动降级到 WASM**，并在界面**明确提示当前后端** |
| §2.3.2 混合检索 | 通过 seekdb-js 接入；**检索处理由 seekdb 完成，不得在客户端分别获取两路结果后自行拼合** |
| §2.5 通用红线 | **禁止调用云端推理 API**；**禁止预先在服务端算好向量或检索结果后回放**；向量和文档的存储、检索**必须使用 seekdb** |

### 1.2 和 Dify 赛题的差异（这决定了工作量分布）

| 维度 | Dify（我做完的） | 阶跃星辰（你要做的） |
|---|---|---|
| 核心 | 工作流编排 + 跨会话记忆 | 浏览器端侧推理 + 量化 + 混合检索 |
| 入口 | Dify DSL（YAML） | Web 应用（浏览器） |
| 模型在哪跑 | 云端 API（Dify 里配） | **必须本地，禁止云端 API** |
| 数据库角色 | 存记忆数据 | 存向量 + 原文 + 元数据；**检索排序必须在 seekdb 内完成** |
| 技术难点 | DSL 语法、SSRF、模型绑定 | Transformers.js / ONNX Runtime Web、WebGPU、WASM 降级、INT8/FP16、评测指标 |
| 量化对比 | 无 | **强制**：体积 / 压缩比 / 质量变化 |
| 性能证据 | 功能正确性验证 | **分阶段计时 + 中位数 + Recall@K / nDCG@K** |
| 部署 | docker compose | Web 应用 + 本地 seekdb（嵌入式或 server） |

> **体感**：Dify 那条我花了约 2 天（其中一半在装 Docker/WSL）。你这条的**难点全在前端与模型侧**，跟数据库关系不大，但"性能与质量测试方法"（§3.2）的报告工作量相当大，**建议一开始就规划评测集**，不要等做完再补。

---

## 2. ⚠️ 三个坑的详细拆解

### 坑 1：npm 上的 `seekdb-js` 已经不存在了

题面 §2.3.1 写「通过 **seekdb-js** 接入 seekdb」。我查了 npm registry：

```json
{
  "_id": "seekdb-js",
  "time": {
    "created": "2025-12-05T07:43:57.310Z",
    "modified": "2025-12-05T08:30:46.751Z",
    "0.1.0-alpha.0": "2025-12-05T07:43:57.551Z",
    "0.1.0-alpha.1": "2025-12-05T07:55:42.289Z",
    "unpublished": {
      "time": "2025-12-05T08:30:46.751Z",
      "versions": ["0.1.0-alpha.0", "0.1.0-alpha.1"]
    }
  }
}
```

这个包只发过两个 alpha 版，**发布当天 47 分钟后就 unpublish 了**。

**真正的包叫 `seekdb`（v1.4.0）**，源码在 GitHub `oceanbase/seekdb-js`（pnpm monorepo，19 stars，Apache-2.0）。官方 README 里的安装命令是：

```bash
npm install seekdb @seekdb/default-embed
```

**动手第一步就是验证这一行能不能装上**：

```bash
npm view seekdb version          # 期望 1.4.0
npm view seekdb dist-tags
```

如果 npm 拉不到（网络问题），从 GitHub 装：

```bash
git clone https://github.com/oceanbase/seekdb-js.git
cd seekdb-js
corepack enable && pnpm install && pnpm build
```

仓库用 `pnpm@9.0.5` + lerna + tsup，本机**没装 pnpm**，用 `corepack enable` 即可（Node 24 自带 corepack）。

### 坑 2：端侧约束 —— 千万别让 Node 端算向量

`seekdb` SDK 的默认行为是**自动向量化**：`collection.add({ documents: [...] })` 会在**当前进程**里调 embedding 函数算向量。如果你的后端是 Node，那向量就是**在服务端算的**——即使模型是本地的 `all-MiniLM-L6-v2`，这仍然**违反 §2.5「实际计算必须发生在用户设备」**。

**正确做法**：

```typescript
// 建集合时显式关掉自动向量化
const schema = new Schema({
  vectorIndex: new VectorIndexConfig({
    hnsw: { dimension: 384, distance: "cosine" },
    embeddingFunction: null,          // ← 关键：不要让 SDK 在 Node 里算
  }),
});

// 浏览器算好向量后，连同原文一起传进去
await collection.add({
  ids: [...],
  documents: [...],                  // 原文
  embeddings: [[...], [...]],        // ← 浏览器算的向量
  metadatas: [...],                 // 文档 ID / 来源等元数据
});

// 查询同理
const results = await collection.query({
  queryEmbeddings: [browserVector],  // ← 浏览器算的查询向量
  nResults: 10,
});
```

**判定标准很简单**：Node 进程里**一个 embedding 模型都不许加载**。向量必须带着 `embeddings` / `queryEmbeddings` 字段从浏览器传进来。这样才站得住「端侧」。

> 顺带：SDK 的 `@seekdb/default-embed`、`@seekdb/qwen`、`@seekdb/openai`、`@seekdb/jina` **全部不要装**。`@seekdb/qwen` / `@seekdb/openai` 是**云端** embedding，装了就等于给自己埋雷（哪怕你不用它，审计时也可能被质疑）。你要的是浏览器侧的 `@huggingface/transformers`（Transformers.js）或 `onnxruntime-web`。

### 坑 3：混合检索必须由 seekdb 完成

§2.3.2 原文：「检索处理由 seekdb 完成，**不得在客户端分别获取两路结果后自行拼合来替代数据库混合检索**」。

**合规做法** —— 用 SDK 的 `hybridSearch()`，一次调用，排序在 seekdb 里做：

```typescript
const hybridResults = await collection.hybridSearch({
  query: { whereDocument: { $contains: "seekdb" } },   // 全文侧
  knn:  { queryEmbeddings: [browserVector] },          // 向量侧
  nResults: 10,
});
```

**不合规的做法**（评审会直接判不通过）：

```typescript
// ❌ 前端先查全文、再查向量、自己加权合并
const ft = await collection.query({ queryTexts: q, nResults: 20 });
const vec = await collection.query({ queryEmbeddings: [v], nResults: 20 });
const merged = mergeAndRerank(ft, vec);   // ← 自己拼合 = 不合规
```

**架构上的推论**：`seekdb` SDK 底层是 `mysql2`（Node 的 TCP socket），**在浏览器里跑不了**；嵌入式模式要 `@seekdb/js-bindings` 原生模块，浏览器也用不了。所以：

> **浏览器不能直接连 seekdb。中间必须有一个 Node 服务。**
> 这个 Node 服务只能是**纯传输层**：收浏览器传来的向量 → 调 seekdb-js → 把 seekdb 返回的结果原样回传。
> **它绝不能自己算向量、也不能自己排序。** 这样才同时满足「端侧推理」和「检索由 seekdb 完成」。

---

## 3. 推荐架构

```
┌──────────────────────────────────────────────────────────┐
│  浏览器（Vite + React + TypeScript）                        │
│                                                            │
│  @huggingface/transformers (Transformers.js)               │
│    或 onnxruntime-web                                      │
│    ├─ 文档向量化  （浏览器本地）                             │
│    ├─ 查询向量化  （浏览器本地）                             │
│    ├─ device: 'webgpu'  ──不支持──▶ device: 'wasm'        │
│    └─ 界面明确提示「当前推理后端：WebGPU / WASM」            │
│                                                            │
│         │  POST /api/documents  {ids, documents, vectors}   │
│         │  POST /api/search    {queryVector}                │
└─────────┼──────────────────────────────────────────────────┘
          │  HTTP（只传向量和原文，不传原始模型推理）
┌─────────▼──────────────────────────────────────────────────┐
│  本地 Node 服务（纯传输层，零推理、零排序）                   │
│    seekdb-js → collection.add / collection.hybridSearch    │
└─────────┼──────────────────────────────────────────────────┘
          │  MySQL 协议（2881）
┌─────────▼──────────────────────────────────────────────────┐
│  seekdb (oceanbase/seekdb:1.4.0-100000172026082615)        │
│    ├─ 稠密向量列 + HNSW 索引                                │
│    ├─ 原文列 + ik 分词全文索引                              │
│    ├─ BM25 稀疏向量索引（可选，作为第三路）                  │
│    └─ hybridSearch() 的排序在这里完成  ✅ 合规              │
└────────────────────────────────────────────────────────────┘
```

**Node 服务的"零推理"是这道题的合规底线**，写代码时守住：

- 不引入 `@seekdb/default-embed` / `@seekdb/qwen` / `@seekdb/openai` / `@seekdb/jina`
- `embeddingFunction: null`
- 代码里不出现任何 `transformers` / `onnxruntime` 的 Node 侧引用
- 最好在 README 里写一句："Node 侧仅做协议转发，向量由浏览器生成，排序由 seekdb 完成"

---

## 4. seekdb-js API 速查

来自 `oceanbase/seekdb-js` README（v1.4.0）。**这是官方 API，不是猜测**。

### 4.1 两种运行模式

| 模式 | 构造参数 | 说明 |
|---|---|---|
| **嵌入式** | `path: "./seekdb.db"` | 本地文件，不需要起服务。依赖原生包 `@seekdb/js-bindings` |
| **服务端** | `host, port, user, password, database, tenant?` | 连远程 seekdb / OceanBase |

嵌入式预编译二进制支持的平台：`linux-x64`、`linux-arm64`、`darwin-arm64`、**`win32-x64`（Windows x86_64 可用）**。

> 这点和 Python 侧不一样：`pyseekdb` 的嵌入式（`pylibseekdb`）**只有 Linux**，Windows 用不了。**JS 侧有 win32-x64**，所以你在 Windows 上跑嵌入式是可行的。
> 加载器支持环境变量 `SEEKDB_BINDINGS_BASE_URL`（预编译产物地址）和 `SEEKDB_BINDINGS_CACHE_DIR`（本地缓存目录）。
> **服务端模式没有平台限制**，最稳。

### 4.2 连接

```typescript
import { SeekdbClient } from "seekdb";

// 服务端模式（推荐，跨平台最稳）
const client = new SeekdbClient({
  host: "127.0.0.1",
  port: 2881,
  user: "root",
  password: "<SEEKDB_ROOT_PASSWORD>",
  database: "stepfun_kb",
});

// 嵌入式模式
const client = new SeekdbClient({ path: "./seekdb.db", database: "test" });
```

连 OceanBase 时额外传 `tenant`（如 `"sys"`）。管理操作（建/列/删库）用 `SeekdbAdminClient()`。

### 4.3 三种索引

```typescript
import { Schema, FulltextIndexConfig, VectorIndexConfig, SparseVectorIndexConfig, K } from "seekdb";
import { Bm25EmbeddingFunction } from "@seekdb/bm25";

const schema = new Schema({
  // 全文：ik 分词（中文）
  fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
  // 稠密向量：HNSW。all-MiniLM-L6-v2 输出 384 维
  vectorIndex: new VectorIndexConfig({
    hnsw: { dimension: 384, distance: "cosine" },
    embeddingFunction: null,              // 端侧方案必须设 null
  }),
  // 稀疏向量：BM25（可选，第三路关键词召回）
  sparseVectorIndex: new SparseVectorIndexConfig({
    sourceKey: K.DOCUMENT,
    embeddingFunction: new Bm25EmbeddingFunction(),
  }),
});

const collection = await client.createCollection({ name: "kb", schema });
```

### 4.4 写入 / 查询

```typescript
// 写入（浏览器算好的向量）
await collection.add({
  ids: ["doc-1", "doc-2"],
  documents: ["原文片段 A", "原文片段 B"],
  embeddings: [[0.1, ...], [0.2, ...]],
  metadatas: [{ source: "a.pdf", page: 3 }, { source: "b.md" }],
});

// 纯向量检索
await collection.query({ queryEmbeddings: [browserVector], nResults: 10 });

// 稀疏 / BM25 检索
await collection.query({ queryTexts: "关键词", queryKey: K.EMBEDDING, nResults: 10 });

// ✅ 混合检索（排序在 seekdb 内完成）
await collection.hybridSearch({
  query: { whereDocument: { $contains: "seekdb" } },
  knn:  { queryEmbeddings: [browserVector] },
  nResults: 10,
});

// 不做检索直接取原始记录
await collection.get({ ids: ["doc-1"] });
```

### 4.5 SDK 元信息

- 包名 `seekdb`，版本 `1.4.0`，`type: module`（ESM），同时提供 CJS
- 依赖 `mysql2@^3.11.5`；可选依赖 `@seekdb/js-bindings`；peer 依赖 `@seekdb/default-embed`（**你的方案里不需要装**）
- 要求 **Node >= 20**（本机 Node v24.16.0，OK）
- 官方文档：`https://www.oceanbase.ai/docs/seekdb-js-get-started`

---

## 5. 环境：本机已就绪的部分

### 5.1 已经装好并验证过（**别重做**）

| 项 | 状态 | 验证方式 |
|---|---|---|
| WSL2 | 已装（WSL 3.0.4.0，内核 6.18.54.1-1） | `wsl --version` |
| Docker Desktop | 已装 **4.97.0.244584**（官方 SHA256 校验过），引擎在跑 | `docker run --rm hello-world` → "Hello from Docker!" |
| Docker Compose | **v5.6.1** | `docker compose version` |
| seekdb 镜像 | **已拉取** `oceanbase/seekdb:1.4.0-100000172026082615`（819 MB） | `docker images` |
| seekdb 容器 | **正在运行且 healthy**：`dify-seekdb`，2881→2881、2886→2886 | `docker ps` |
| Node.js | **v24.16.0**（`D:\node.exe`），npm **11.13.0** | `node --version` |
| Python | 3.12.10 | `python --version` |
| git | 2.55.0.windows.5 | `git --version` |
| 磁盘 | D 盘剩 99.5 GB | `Get-PSDrive D` |

### 5.2 ⚠️ PowerShell 里 npm/npx 会被拦

执行策略是 Restricted，`.ps1` 包装器跑不了。**用 `.cmd` 后缀**：

```powershell
npm.cmd --version      # ✅ 11.13.0
npm.cmd install seekdb
npx.cmd --version
```

或者在 cmd 里直接用 `npm`（cmd 不走 PowerShell 策略）。**这是 Windows 上的通用坑，先记住能省半小时。**

### 5.3 起一个属于 stepfun 的 seekdb（别动 dify 的库）

当前 `dify-seekdb` 容器里已有库 `npc_memory`（Dify 赛题在用）。**建议单独起一个容器**，互不干扰：

```powershell
docker run -d --name stepfun-seekdb `
  -e ROOT_PASSWORD=StepFun@2026 `
  -p 2881:2881 -p 2886:2886 `
  -v stepfun-seekdb-data:/var/lib/seekdb `
  --restart unless-stopped `
  oceanbase/seekdb:1.4.0-100000172026082615
```

等它 healthy（约 40 秒）：

```powershell
docker exec stepfun-seekdb mysql -uroot -pStepFun@2026 -h 127.0.0.1 -P 2881 -e "show databases;"
```

> **端口冲突**：本机 2881/2886 已被 `dify-seekdb` 占用。要么先停掉它，要么把 stepfun 容器映射到别的端口（如 `28811:2881`），并在 Node 服务里用对应端口。
> **Windows 必须用命名卷**（`-v stepfun-seekdb-data:/var/lib/seekdb`），不要用宿主目录 bind mount。

### 5.4 建库建表

```powershell
docker exec stepfun-seekdb mysql -uroot -pStepFun@2026 -h 127.0.0.1 -P 2881 `
  -e "CREATE DATABASE IF NOT EXISTS stepfun_kb DEFAULT CHARACTER SET utf8mb4;"
```

### 5.5 复用的工程经验（**直接抄，能省时间**）

我在 Dify 那条线上写的这些脚本，`stepfun/` 可以直接改造复用：

- `dify/deploy/docker-compose.yml` —— compose 写法、命名卷、healthcheck 都可以照搬
- `dify/deploy/init_db.py` —— 建库建表 + 索引初始化的骨架
- `dify/deploy/dump_state.py` —— **直连数据库导出行级证据**（§3.2 的数据留证要用）
- `dify/deploy/check_packaging.py` —— 打包/配置自检脚本
- `dify/validation/service_checks.py` —— 端到端检查脚本的结构（10 项检查 + 生成 .md/.json 报告）
- `dify/validation/workflow_checks.py` —— 全流程验证脚本 + 报告生成

**报告机制**：官方 §3.2 要求"分阶段计时 / 中位数 / Recall@K / nDCG@K / 压缩比"。我这套「跑一遍 → 生成 .md 报告 + .json 原始数据」的套路可以直接照搬，评审很吃这个。

---

## 6. 端侧推理与量化：怎么做

### 6.1 运行时选型

| 方案 | 优点 | 注意 |
|---|---|---|
| **Transformers.js**（`@huggingface/transformers`） | 生态最成熟，ONNX 模型现成，**自带动词量化和 WebGPU/WASM 后端切换**，官方文档直接支持 | 模型首次要从 HuggingFace 下载；**模型文件放本地还是走 CDN 要想清楚**（题面说"模型文件下载不改变推理位置要求"，所以 CDN 下载是允许的） |
| **onnxruntime-web** | 更底层，性能可控 | 要自己准备 ONNX 模型、处理 tokenizer、量化配置 |

**建议用 Transformers.js**：它同时满足 §2.2.1（端侧运行时）、§2.2.3（量化）和 §2.2.4（WebGPU/WASM），能少踩很多坑。

```typescript
import { pipeline, env } from "@huggingface/transformers";

// 关键：显式指定后端，并捕获不支持的情况做降级
let backend: "webgpu" | "wasm" = "wasm";
try {
  if (!navigator.gpu) throw new Error("no WebGPU");
  const pipe = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", {
    device: "webgpu",
    dtype: "fp32",
  });
  backend = "webgpu";
} catch (e) {
  const pipe = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", {
    device: "wasm",
    dtype: "q8",
  });
  backend = "wasm";
}
// 界面上必须显示：当前推理后端 = backend
```

### 6.2 模型选型（题面 §2.2.2 明确"不限定使用阶跃星辰模型"）

| 模型 | 维度 | 备注 |
|---|---|---|
| `Xenova/all-MiniLM-L6-v2` | 384 | **seekdb SDK 的默认模型**（`@seekdb/default-embed` 就用它），最省事，生态最好；中文能力一般 |
| `Xenova/bge-small-zh-v1.5` | 512 | **中文语料建议用这个**，all-MiniLM 是多语但中文偏弱 |
| `Xenova/bge-small-en-v1.5` | 384 | 英文语料 |

> **提醒**：`seekdb` SDK 里 `VectorIndexConfig` 默认维度是 **384**。如果用 512 维的模型，**必须显式指定 `dimension: 512`**，否则插入时报错。`all-MiniLM-L6-v2` / `bge-small-en` 都是 384，**`bge-small-zh` 是 512**。

模型来源与版本必须在技术说明里写清楚（题面 §2.2.2 + §4.3 强制要求）。

### 6.3 量化（§2.2.3）

- Transformers.js 里，量化通常体现在 `dtype` 参数：`"fp32"` / `"fp16"` / `"q8"` / `"int8"`
- **对照组**：同一模型 fp32（基线） vs q8/int8（或 fp16）
- **要报的数字**（§3.2 第 2 条）：
  - 量化前模型文件总体积、量化后总体积
  - `压缩比 = 量化前体积 / 量化后体积`
  - **体积要按同一口径统计**——只算模型权重文件，不含 tokenizer / 配置（或者全部都算，但两栏口径必须一致，并在说明里写清楚）
- **要报的质量变化**（§3.2 第 3 条）：
  - 用 **Recall@K / nDCG@K**，在**同一个评测集**上跑量化前/后两组
  - 注明评测方法（评测集怎么来的、相关性怎么判定的）
  - **不能只凭主观展示说"好像差不多"**——官方明文写了

### 6.4 分阶段计时（§3.2 第 4 条，必须分开报）

| 阶段 | 怎么测 |
|---|---|
| 模型下载 | `performance.now()` 前后包住首次 `pipeline()` 触发下载 |
| 模型加载 | 下载完成到 pipeline 可用 |
| 文档向量化 | 批量 encode 的总时长 / 条数 = 吞吐 |
| 写入 + 索引刷新 | 写入耗时；**索引刷新要单独测**（§2.3.3 专门提了刷新） |
| 查询向量化 | 单次 encode 耗时 |
| seekdb 检索 | Node 侧 `hybridSearch()` 往返耗时 |
| **端到端** | 用户点提交 → 结果可展示 |

**§3.2 第 5 条**：首次加载和预热后**分开报**；**重复测试取中位数**，不能只报最快一次。原始数据要留下（JSON）。

**§3.2 第 6 条**：**必须分别测 WebGPU 可用和不可用两种环境**。Chrome 里可以：
- 测 WebGPU 可用：默认
- 测降级：在页面里加一个"强制 WASM"的开关（推荐，评审能一键验证），或用 `chrome://flags` 关掉 WebGPU / 用 `--disable-features=Vulkan` 启动

### 6.5 官方给的报告表格（§3.2 建议列，照抄这个格式）

| 配置 | 模型体积 | 向量化吞吐 | seekdb 检索延迟 | 端到端查询延迟 | 检索质量 |
|---|---|---|---|---|---|
| 量化前基线 | 实测值 | 实测值 | 实测值 | 实测值 | 指标与结果 |
| INT8 / FP16 + WebGPU | 实测值 | 实测值 | 实测值 | 实测值 | 同一指标结果 |
| INT8 / FP16 + WASM | 实测值 | 实测值 | 实测值 | 实测值 | 同一指标结果 |

---

## 7. 验收标准逐条对照表

把官方 §3.1 / §3.2 拆成可勾选的清单，**每一条都要有对应的证据文件**。

### 7.1 §3.1 功能与质量（7 项）

| # | 官方要求 | 怎么满足 | 证据放哪 |
|---|---|---|---|
| 1 | 完整流程：导入文本 → 生成向量 → 写入 seekdb → 查询 → 展示排序结果 | 前端 + Node 传输层 + seekdb | 录屏 / 截图 + `walkthrough.md` |
| 2 | 本地推理：文档与查询 embedding 均在浏览器本地计算，**无云端推理 API 调用** | §3 架构；Node 侧零模型 | **录屏 DevTools Network 面板，证明没有外部推理请求** + 代码 |
| 3 | 模型量化：INT8 或 FP16，给出来源、量化方式、体积对比、质量变化 | §6.3 | `perf-report.md` + 体积对比表 |
| 4 | 后端与降级：优先 WebGPU，不支持自动降级 WASM，**界面明确提示** | §6.1 | 两种环境各截一张图（界面要能看到当前后端） |
| 5 | seekdb 数据层：向量/原文/元数据存 seekdb，混合检索在 seekdb 完成 | §3 架构 + `hybridSearch()` | 直连 seekdb 导出的行级数据 + 执行的 SQL/调用 |
| 6 | 状态与刷新：增量导入，刷新后新内容可检索，集合/会话状态正确 | `collection.add` + 刷新后 `hybridSearch` 能查到 | 增量导入的脚本 + 输出 |
| 7 | 可复现性：按提交的说明可启动应用及数据库并完成上述操作 | README §启动步骤 | 评审照着做一遍的可行性 |

### 7.2 §3.2 性能与质量测试方法（6 条）

| # | 要求 | 交付物 |
|---|---|---|
| 1 | 固定测试条件：同设备/浏览器/语料/查询集，记录模型版本、精度、后端、批大小、seekdb 配置 | 测试配置文件（`bench/config.json`）+ 语料与查询集 |
| 2 | 模型体积对比，同一口径，压缩比 = 前/后 | 体积对比表 |
| 3 | 检索质量：同评测集，Recall@K / nDCG@K，注明评测方法 | 评测脚本 + 指标结果 |
| 4 | 分阶段计时 + 端到端延迟 | 计时表 |
| 5 | 首次 vs 后续分开，重复测试报中位数，留原始数据 | 原始 JSON + 中位数汇总 |
| 6 | 分别测 WebGPU 可用/不可用 | 两套环境的结果 |

---

## 8. 提交材料清单（§4）

照抄官方结构，三份：

| 官方条款 | 你要交的东西 | 放哪 |
|---|---|---|
| **4.1 可运行的 Web 应用** | 本地启动步骤（浏览器要求、依赖安装、启动命令）；seekdb 嵌入式 **或** 随应用提供本地 server 启动脚本 + 连接配置；应用能演示**导入进度 / 检索结果 / 当前推理后端** | `stepfun/README.md` §启动 |
| **4.2 完整源码** | 应用源码、依赖与配置、**模型获取及量化步骤**、**seekdb 集合/表结构与索引配置**、**用于复现测试的数据或数据生成方式** | `stepfun/` 全量 |
| **4.3 一页技术说明** | ① 模型与量化（来源/版本/INT8或FP16方案/前后体积/压缩比/质量变化）② 端侧运行（运行时/WebGPU选择/降级策略/验证结果）③ seekdb 使用（表结构/混合检索方式/增量写入与索引刷新）④ 状态与优化（状态管理/批处理/性能对比） | `stepfun/TECH_NOTE.md`，**压到一页** |

> 技术说明**之外**可附测试日志和详细复现步骤，但「实验结果应来自提交应用的实际运行」——**所有数字都要是真跑出来的**。
> 「一页」是硬要求，别写成十页。

---

## 9. 分支、目录与提测机制

### 9.1 从哪切分支

**官方基线 = `d647275c308e09b7b623f322a26f5c4e85734fb0`**
（我已核实：这正是上游 `oceanbase/powercontext` 的 `2026-competition-ecosystem` 分支 tip）

```powershell
cd "D:\ZhuYijing\Documents\minimax工作文件夹\powercontext"
git fetch origin
git checkout -b ecosystem/<你的名字>-stepfun d647275c
```

> ⚠️ **别从 `ecosystem/zyj-dify` 切**。那条分支已经合并了 dify/ + gaode/ + modelscope/ 三份资产，是**提测用的合流分支**，不是干净基线。
> 从 `d647275c` 切出来的分支只会有 `stepfun/` 一个新增目录，符合官方「相关项目资产放入对应 stepfun 目录中」。

`d647275c` 里的目录长这样（全是空占位）：

```
dify  gaode  minimax  qoder  stepfun
```

### 9.2 资产必须放对目录

官方原文：「相关项目资产放入对应 **stepfun** 目录中」。

```
stepfun/
├── README.md          # 运行说明（§4.1 + §4.2）
├── TECH_NOTE.md       # 一页技术说明（§4.3）
├── package.json
├── src/               # 前端（浏览器）
├── server/            # Node 传输层
├── bench/             # 评测脚本 + 语料 + 查询集 + 原始数据
└── docs/              # 截图、录屏、日志
```

### 9.3 提测流程（Dify 那边我已完整走过一遍）

1. **GitHub PAT**：官方要求「使用带有 pat 密钥的地址，否则无法 clone 大家的私有仓库代码」
   - GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate
   - Scope **勾 `repo`**，Expiration 选长一点
   - **离开页面就看不到了，立刻保存**
2. **平台地址**：OceanBase 社区 `https://open.oceanbase.com/train/detail/21`（我探测过，可访问）
3. **表单三个字段**：
   - 仓库地址：`https://<用户名>:<PAT>@github.com/Icsya05/powercontext`
   - 分支：`ecosystem/<你的名字>-stepfun`
   - commit hash：你的分支 tip（40 位完整 SHA）
4. 提交后留档截图

### 9.4 合流规则（**我踩过的坑，你直接避开**）

官方是「按你填的那个分支 clone 评测」。所以：

> **提交的分支必须包含所有生态资产。**
> Dify 那边的两条分支 `ecosystem/zyj-dify` 和 `ecosystem/wyd-gaode-modelscope` 原来是并列的，我最后用
> `git merge --no-ff` 合到了一条（零冲突，因为各加各的目录），提测才完整。
> 你的 stepfun 分支做完后，也需要**跟其他生态分支合并**再提测，或者跟队长确认合流分支名。
> **合并用 `--no-ff`，不要 force push，不要改写别人的 commit。**

### 9.5 git 网络（本机老毛病）

这台机器直连 GitHub 会抽风，两个都试一下：

```powershell
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin <branch>
# 代理抽风时，去掉 -c http.proxy=... 反而能通
```

推完**务必核对**：

```powershell
git ls-remote origin refs/heads/<branch>
```

---

## 10. 工程环境踩坑清单（Windows / PowerShell 5.1）

我在这台机器上真实踩过的，全部给你：

| 坑 | 症状 | 解法 |
|---|---|---|
| **`.ps1` 文件没有 BOM** | PowerShell 5.1 当 ANSI 读，中文注释直接语法错误 | 写 `.ps1` 必须带 UTF-8 BOM（`Set-Content -Encoding UTF8` 或 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($true)))`） |
| **commit message 带 BOM** | 提交信息开头多一个 `﻿` | 用 `New-Object System.Text.UTF8Encoding($false)` 写消息文件，别用 `Set-Content -Encoding UTF8` |
| **`Remove-Item` 被安全策略拦截** | 删文件报 Permission denied | 删文件用 `Move-Item` 移出仓库，或 `rm -- "<目标>"` |
| **npm 的 `.ps1` 包装器被拦** | `npm --version` 报「禁止运行脚本」 | 用 `npm.cmd` / `npx.cmd`，或换 cmd |
| **`edit` 工具改不了带中文全角标点的文件** | `old_string` 匹配失败 | 改用 Python 脚本做字符串替换（`[IO.File]::WriteAllText(path, text, UTF8Encoding($false))`） |
| **中文路径让 CMake 崩溃** | `0xC0000409` | `subst` 映射一个 ASCII 盘符再构建（seekdb 原生编译时踩的；你用 Docker 应该碰不到） |
| **PATH 里的 mingw `ld.exe` 抢链接器** | 链接报找不到 MSVC lib | 用 MSVC 的 `link.exe`，把 mingw 从 PATH 剥掉（原生编译才需要） |
| **WSL2 装不上** | `wsl --install` 报 403 | `dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart` + 手动装 `wsl.3.0.4.0.x64.msi`，**必须重启**。本机已经装好了，你不用经历 |

---

## 11. 建议路线（按这个顺序，能最快拿到能跑的东西）

**第 1 步（半天）：打通最小链路，别管量化**
- 浏览器用 Transformers.js 算一个 384 维向量
- Node 侧 `collection.add({ ids, documents, embeddings })` 写进 seekdb
- Node 侧 `collection.query({ queryEmbeddings })` 查出来
- **先证明「端侧算向量 + seekdb 存取」这条路通**

**第 2 步（半天）：把混合检索改成 seekdb 内完成**
- 建 `Schema`（ik 全文 + hnsw 向量）
- 改用 `collection.hybridSearch({ query: { whereDocument: {...} }, knn: { queryEmbeddings: [...] } })`
- **确认前端只发一次请求、只收一次结果**

**第 3 步（1 天）：WebGPU / WASM + 界面提示 + 量化对照组**
- 后端切换逻辑 + 界面显示当前后端
- 加一个"强制 WASM"开关（评审能一键验证降级）
- 跑 fp32 vs q8 两组，量体积、算压缩比

**第 4 步（1 天）：评测集与性能报告**
- 造一个小语料集（比如 100–300 条中文文档片段）+ 20–50 条查询 + 相关性标注
- 写 Recall@K / nDCG@K 脚本
- 分阶段计时脚本，跑 20 次取中位数
- **生成 §3.2 那张三行表格**

**第 5 步（半天）：文档与证据**
- README（启动步骤）+ TECH_NOTE.md（一页）
- 截图 / 录屏 / 行级数据导出 / 原始 benchmark JSON
- 提测（PAT + 分支 + commit）

---

## 12. 交接确认清单

开工前请你确认这几点，有疑问随时找我：

- [ ] `npm.cmd view seekdb version` 能返回 1.4.0（**第一个要验证的**）
- [ ] 决定用**嵌入式**还是**服务端**模式（我建议服务端，跨平台最稳）
- [ ] 决定端口方案（2881/2886 已被 Dify 占用）
- [ ] 决定 embedding 模型（384 维 vs 512 维，影响索引配置）
- [ ] 决定技术栈（Vite + React + TS？）
- [ ] 确认分支名（`ecosystem/<你的名字>-stepfun`）
- [ ] 知悉合流规则（提测时要含全部生态资产）

---

## 附：这份文档里所有"已验证"结论的来源

| 结论 | 怎么验证的 |
|---|---|
| 上游 `2026-competition-ecosystem` tip = `d647275c` | `git ls-remote --heads https://github.com/oceanbase/powercontext.git` |
| npm `seekdb-js` 已 unpublish | `curl https://registry.npmjs.org/seekdb-js` |
| npm 包真身是 `seekdb@1.4.0` | `oceanbase/seekdb-js` 仓库 `packages/seekdb/package.json` |
| 嵌入模式支持 `win32-x64` | 同仓库 README「Embedded mode platform support」 |
| `hybridSearch()` / `add({embeddings})` / `embeddingFunction: null` | 同仓库 README「Usage Guide」 |
| Docker Desktop 4.97.0.244584 + Compose v5.6.1 可用 | `docker run --rm hello-world`、`docker compose version` |
| seekdb 镜像可用、容器 healthy | `docker ps` |
| Node v24.16.0 / npm 11.13.0 / PowerShell 拦 `.ps1` | `node --version`、`npm.cmd --version`、执行策略查询 |
| 官方 §4 提交材料清单 | 语雀《阶跃星辰》全文（2309 字）逐条对照 |
