# Agent 交接提示词 · 阶跃星辰赛题（OceanBase 2026 大赛）

> 用法：把下面 `=== 提示词开始 ===` 到 `=== 提示词结束 ===` 之间的全部内容，**整段粘贴**给一个新开的 agent 会话。
> 这份提示词是自包含的：它不依赖任何前置对话，也不假设你知道我做过什么。

---

=== 提示词开始 ===

你接手 **2026 OceanBase 数据库大赛「阶跃星辰」赛题**的开发，把一个可运行、可复现、可提测的作品做出来。

## 0. 你的任务一句话

在 `stepfun/` 目录里交付一个**在浏览器本地完成 embedding 推理**的迷你知识库 Web 应用：用户导入文本 → 浏览器本地向量化 → 写入 **seekdb** → 查询时浏览器本地生成查询向量 → **由 seekdb 完成向量 + 全文混合检索** → 展示排序结果与原文。同时交付量化对比（INT8/FP16）与性能/质量实测报告。

## 1. 为什么是这个任务（背景）

同一支队伍的另一条赛题「Dify」已经完成并提测。你这条赛题的**技术栈完全不同**，不要沿用 Dify 的思路：

| 维度 | Dify（已完成，不要管） | 阶跃星辰（你的任务） |
|---|---|---|
| 核心 | 工作流编排 + 跨会话记忆 | 浏览器端侧推理 + 量化 + 数据库内混合检索 |
| 入口 | Dify DSL（YAML） | Web 应用（浏览器） |
| 模型在哪跑 | 云端 API（Dify 里配） | **必须本地，禁止云端推理 API** |
| 数据库角色 | 存记忆数据 | 存向量 + 原文 + 元数据；**排序必须在 seekdb 内完成** |
| 强制对比项 | 无 | **量化前后体积 / 压缩比 / 检索质量变化** |
| 性能证据 | 功能正确性 | **分阶段计时 + 中位数 + Recall@K / nDCG@K** |

## 2. 官方题面（权威来源，请自己再核一遍）

- **题面原文**：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9 （语雀《阶跃星辰》，2309 字，2026-10-26 更新）
- **提交材料说明**：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lhfslihtnnb8yqh6 （《Dify》里 §4 提交材料的结构与阶跃星辰 §4 同构，可参考写法）
- **GitHub 使用说明（PAT 与提测）**：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts
- **测评平台**：https://open.oceanbase.com/train/detail/21

> 语雀是 SPA，`web_fetch` 只能拿到空壳，**必须用内置浏览器渲染后再读**。请先加载 `browser-use:control-in-app-browser` skill 再用 Browser 工具。

**题面里最关键的几条原文（务必逐条对照实现）：**

- §2.2.1：用 Transformers.js、ONNX Runtime Web 等端侧运行时，**在用户设备的浏览器中**执行 embedding 推理。**文档向量化和查询向量化均须在本地完成**。
- §2.2.2：模型可自由选择（如 all-MiniLM-L6-v2、bge-small），**必须为可公开获取的开源模型**，并在技术说明中注明来源与版本。
- §2.2.3：采用 **INT8 或 FP16** 方案，说明处理方式，**报告量化前后的模型体积、压缩比及检索质量变化**。
- §2.2.4：**优先使用 WebGPU**，显式配置推理后端；运行环境不支持时**自动降级到 WASM**，并在界面中**明确提示当前使用的后端**。
- §2.3.1：**通过 seekdb-js 接入 seekdb**，创建集合或表，保存向量、原文及文档 ID 等元数据。数据库可采用**嵌入式或本地 server** 方式部署。
- §2.3.2：实现向量与全文混合检索，**检索处理由 seekdb 完成，不得在客户端分别获取两路结果后自行拼合来替代数据库混合检索**。
- §2.3.3：正确处理数据写入和**索引刷新**，确保新导入的文档在刷新完成后能够被检索到。
- §2.3.4：管理知识库的增量写入、集合与会话状态，保证连续导入和切换操作后的检索结果与当前知识库一致。
- §2.5：**禁止调用云端推理 API**；**禁止预先在服务端算好向量或检索结果后回放**，禁止将远程推理伪装为端侧推理；向量和文档的存储、检索**必须使用 seekdb**，不得使用其他数据库或客户端内存检索替代。
- §3.2 性能与质量测试方法：固定测试条件（设备/浏览器版本/语料/查询集，记录模型版本、精度、推理后端、批大小、seekdb 配置）；压缩比 = 量化前体积 / 量化后体积；检索质量用 **Recall@K / nDCG@K** 并注明评测方法；**分阶段计时**（模型下载与加载、文档向量化、写入与索引刷新、查询向量化、seekdb 检索耗时 + 端到端延迟）；**区分首次与后续请求**，重复测试**报中位数**；**分别测 WebGPU 可用与不可用两种环境**。
- §4 提交材料：**4.1 可运行的 Web 应用**（浏览器要求、依赖安装、启动步骤；seekdb 嵌入式或随应用提供本地 server 启动脚本与连接配置；应用需能演示文档导入、向量化进度、检索结果、当前推理后端）；**4.2 完整源码**（源码、依赖与配置、模型获取及量化步骤、seekdb 集合/表结构与索引配置、复现测试的数据或数据生成方式）；**4.3 一页技术说明**（模型与量化 / 端侧运行 / seekdb 使用 / 状态与优化）。

## 3. 三个已确认的雷（提前查过了，照着做就能绕开）

### 雷 1：npm 上的 `seekdb-js` 已经被 unpublish

题面让你用 `seekdb-js`，但该包只发过 `0.1.0-alpha.0` / `0.1.0-alpha.1`，**2025-12-05 发布当天 47 分钟后即被撤下**，现在装不上。

真正的包叫 **`seekdb`（v1.4.0）**，源码在 GitHub `oceanbase/seekdb-js`（pnpm monorepo，Apache-2.0）。

```bash
npm view seekdb version          # 期望 1.4.0 —— 这是第一个验证动作
npm install seekdb
```

若 npm 拉不到（网络问题）：`git clone https://github.com/oceanbase/seekdb-js.git` → `corepack enable && pnpm install && pnpm build`（仓库用 pnpm@9.0.5）。

### 雷 2：SDK 默认在服务端算向量 → 违反"端侧推理"

`collection.add({ documents })` 会在**当前进程**调用 embedding 函数。如果后端是 Node，向量就是在服务端算的，哪怕模型是本地的，**仍然违反 §2.5**。

合规做法：

```typescript
const schema = new Schema({
  vectorIndex: new VectorIndexConfig({
    hnsw: { dimension: 384, distance: "cosine" },
    embeddingFunction: null,          // ← 关键
  }),
});
await collection.add({ ids, documents, embeddings, metadatas });   // embeddings 来自浏览器
await collection.query({ queryEmbeddings: [browserVector], nResults: 10 });
```

**判定标准**：Node 进程里**一个 embedding 模型都不许加载**。向量必须由浏览器通过 `embeddings` / `queryEmbeddings` 传进来。

**不要安装** `@seekdb/default-embed` / `@seekdb/qwen` / `@seekdb/openai` / `@seekdb/jina` —— 后三个是**云端** embedding，装了等于埋雷。你要的是浏览器侧的 `@huggingface/transformers`（Transformers.js）或 `onnxruntime-web`。

### 雷 3：混合检索必须由 seekdb 完成

合规（单次调用，排序在 seekdb 内）：

```typescript
const hybridResults = await collection.hybridSearch({
  query: { whereDocument: { $contains: "seekdb" } },   // 全文侧
  knn:  { queryEmbeddings: [browserVector] },           // 向量侧
  nResults: 10,
});
```

不合规（前端两路结果自己拼 → 直接不合规）：

```typescript
const ft  = await collection.query({ queryTexts: q, nResults: 20 });
const vec = await collection.query({ queryEmbeddings: [v], nResults: 20 });
const merged = mergeAndRerank(ft, vec);      // ← 禁止
```

**架构推论**：`seekdb` SDK 底层是 `mysql2`（Node 的 TCP socket），浏览器跑不了；嵌入式模式要 `@seekdb/js-bindings` 原生模块，浏览器也用不了。**所以浏览器不能直连 seekdb，中间必须有一个 Node 服务**，而它只能是**纯传输层**：收浏览器传来的向量 → 调 seekdb-js → 把 seekdb 的结果原样回传。**它绝不能自己算向量，也不能自己排序。**

## 4. seekdb-js API 速查（来自官方 README，非猜测）

**两种模式**

| 模式 | 构造参数 | 说明 |
|---|---|---|
| 嵌入式 | `path: "./seekdb.db"` | 本地文件，不需起服务；依赖原生包 `@seekdb/js-bindings`。预编译二进制支持 `linux-x64` / `linux-arm64` / `darwin-arm64` / **`win32-x64`（Windows 可用）**。加载器支持 `SEEKDB_BINDINGS_BASE_URL`、`SEEKDB_BINDINGS_CACHE_DIR` |
| 服务端 | `host, port, user, password, database, tenant?` | 连远程 seekdb / OceanBase。**跨平台最稳，推荐** |

```typescript
import { SeekdbClient } from "seekdb";
const client = new SeekdbClient({
  host: "127.0.0.1", port: 2881, user: "root",
  password: "<SEEKDB_ROOT_PASSWORD>", database: "stepfun_kb",
});
```

**三种索引**

```typescript
import { Schema, FulltextIndexConfig, VectorIndexConfig, SparseVectorIndexConfig, K } from "seekdb";
import { Bm25EmbeddingFunction } from "@seekdb/bm25";

const schema = new Schema({
  fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),        // 中文全文
  vectorIndex: new VectorIndexConfig({
    hnsw: { dimension: 384, distance: "cosine" },
    embeddingFunction: null,
  }),
  sparseVectorIndex: new SparseVectorIndexConfig({                            // 可选第三路
    sourceKey: K.DOCUMENT,
    embeddingFunction: new Bm25EmbeddingFunction(),
  }),
});
const collection = await client.createCollection({ name: "kb", schema });
```

**其他 API**：`collection.add({ ids, documents, embeddings, metadatas })` / `collection.query({ queryEmbeddings | queryTexts, queryKey, nResults })` / `collection.get({ ids })` / `collection.hybridSearch({ query, knn, nResults })`。管理操作用 `SeekdbAdminClient()`。

**SDK 元信息**：包名 `seekdb`，版本 `1.4.0`，ESM（`type: module`）+ CJS 双出，依赖 `mysql2@^3.11.5`，可选依赖 `@seekdb/js-bindings`，要求 **Node >= 20**。官方文档：https://www.oceanbase.ai/docs/seekdb-js-get-started

**维度注意**：SDK 默认 `dimension: 384`。`all-MiniLM-L6-v2` / `bge-small-en-v1.5` 是 384 维；**`bge-small-zh-v1.5` 是 512 维**，用它必须显式写 `dimension: 512`，否则插入报错。中文语料建议用 bge-small-zh。

## 5. 环境：以下已经装好并验证过，**不要重做**

| 项 | 状态 |
|---|---|
| WSL2 | 已装（WSL 3.0.4.0，内核 6.18.54.1-1） |
| Docker Desktop | 已装 **4.97.0.244584**（官方 SHA256 校验过），引擎在跑，`docker run --rm hello-world` 通过 |
| Docker Compose | v5.6.1 |
| seekdb 镜像 | 已拉取 `oceanbase/seekdb:1.4.0-100000172026082615`（819 MB） |
| seekdb 容器 | `dify-seekdb` 正在运行且 healthy，2881→2881、2886→2886 |
| Node.js / npm | **v24.16.0**（`D:\node.exe`）/ npm 11.13.0 |
| Python | 3.12.10 |
| git | 2.55.0.windows.5 |
| 磁盘 | D 盘剩 99.5 GB |

**端口冲突**：2881 / 2886 已被 `dify-seekdb` 占用。**不要动 Dify 的容器和 `npc_memory` 库**。给你的库建议另起容器并换端口：

```powershell
docker run -d --name stepfun-seekdb `
  -e ROOT_PASSWORD=StepFun@2026 `
  -p 28811:2881 -p 28816:2886 `
  -v stepfun-seekdb-data:/var/lib/seekdb `
  --restart unless-stopped `
  oceanbase/seekdb:1.4.0-100000172026082615
# 等 healthy（约 40 秒），然后建库
docker exec stepfun-seekdb mysql -uroot -pStepFun@2026 -h 127.0.0.1 -P 2881 `
  -e "CREATE DATABASE IF NOT EXISTS stepfun_kb DEFAULT CHARACTER SET utf8mb4;"
```

> **Windows 必须用命名卷**（`-v stepfun-seekdb-data:/var/lib/seekdb`），不要用宿主目录 bind mount。

## 6. 仓库、分支与提交纪律

- **仓库**：`D:\ZhuYijing\Documents\minimax工作文件夹\powercontext`（私有镜像 `https://github.com/Icsya05/powercontext.git`），已在本地，无需重新 clone。
- **官方基线**：`d647275c308e09b7b623f322a26f5c4e85734fb0` —— 已核实这就是上游 `oceanbase/powercontext` 的 `2026-competition-ecosystem` 分支 tip。基线里的目录全是空占位：`dify/ gaode/ minimax/ qoder/ stepfun/`。
- **你的分支**：从 `d647275c` 切一条新分支，**不要从 `ecosystem/zyj-dify` 切**（那条已合并了 Dify/Gaode/ModelScope 三份资产，是提测合流分支）。

```powershell
cd "D:\ZhuYijing\Documents\minimax工作文件夹\powercontext"
git fetch origin
git checkout -b ecosystem/<你的分支名>-stepfun d647275c
```

- **资产只放 `stepfun/`**（官方要求"相关项目资产放入对应 stepfun 目录中"）。
- **绝对不要动** `dify/`、`gaode/`、`modelscope/`、`minimax/`、`qoder/` 下的任何文件。
- **不许 force push、不许改写他人历史、不许直接推 master**。
- **提测与合流由队长/用户做**，你不需要拿 PAT，也不要 push 到 `ecosystem/zyj-dify`。
- git 网络在本机会抽风，推送时先试带代理，失败就去掉代理重试：
  ```powershell
  git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin <你的分支>
  ```
  推完用 `git ls-remote origin refs/heads/<你的分支>` 核对。

## 7. 硬性约束

1. **不许伪造任何结果。** 所有体积、压缩比、延迟、Recall@K/nDCG@K 数字必须来自**提交应用的实际运行**。库不可达、模型没跑起来，就如实报 FAIL 并写明原因，不要编造。
2. **禁止云端推理、禁止服务端预计算回放**（题面 §2.5 红线）。
3. **混合检索必须在 seekdb 内完成**，不允许前端拼合两路结果（§2.3.2 红线）。
4. **密钥/Token/API Key 只进本机 `.env` 或平台表单**，绝不写进任何提交文件、README、日志、截图。配置示例一律用占位值。
5. **不自行开通付费服务**。模型 API 是唯一可能产生费用的项，需用户自行配置；你的方案是纯本地模型，不应产生模型费用。
6. **Windows / PowerShell 5.1 坑**（真实踩过的）：
   - `.ps1` 文件**必须带 UTF-8 BOM**，否则 PowerShell 5.1 当 ANSI 读导致语法错误。
   - commit message 用 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($false)))` 写，**不要**用 `Set-Content -Encoding UTF8`（会带 BOM）。
   - `Remove-Item` 被本机安全策略拦截 → 删文件用 `Move-Item` 移出仓库，或 `rm -- "<目标>"`。
   - **npm 的 `.ps1` 包装器被拦** → 用 `npm.cmd` / `npx.cmd`，或换 cmd 执行。
   - `edit` 工具对含中文全角标点的文件做 `old_string` 匹配会失败 → 改用 Python 脚本做替换。

## 8. 执行路线（按顺序，别跳）

**第 1 步（半天）｜打通最小链路，先不管量化**
浏览器用 Transformers.js 算 384 维向量 → Node 侧 `collection.add({ ids, documents, embeddings })` 写入 → `collection.query({ queryEmbeddings })` 查回来。**先证明"端侧算向量 + seekdb 存取"这条路通。**

**第 2 步（半天）｜把检索改成 seekdb 内完成**
建 `Schema`（ik 全文 + hnsw 向量），改用 `collection.hybridSearch({ query: { whereDocument: {...} }, knn: { queryEmbeddings: [...] } })`，确认前端**只发一次请求、只收一次结果**。

**第 3 步（1 天）｜WebGPU / WASM + 界面提示 + 量化对照组**
后端切换 + 界面显示当前后端；加一个"强制 WASM"开关（评审能一键验证降级）；跑 fp32 vs q8/int8 两组，量体积、算压缩比。

**第 4 步（1 天）｜评测集与性能报告**
造一个小语料集（100–300 条中文文档片段）+ 20–50 条查询 + 相关性标注；写 Recall@K / nDCG@K 脚本；分阶段计时脚本跑 20 次取中位数；**生成 §3.2 那张三行表格**（量化前基线 / 量化+WebGPU / 量化+WASM）。

**第 5 步（半天）｜文档与证据**
`stepfun/README.md`（启动步骤、依赖、seekdb 启动脚本与连接配置）+ `stepfun/TECH_NOTE.md`（**一页**）+ 截图/录屏/行级数据导出/原始 benchmark JSON。

**第 6 步｜提交**
commit + push 到你自己的分支，把**分支名 + 完整 40 位 commit SHA + 你的改动摘要**汇报出来。提测表单由用户填。

## 9. 交付物与验收标准

**必须落在 `stepfun/` 里**：

```
stepfun/
├── README.md          # 运行说明：浏览器要求、依赖安装、启动步骤、seekdb 启动与连接配置、已知限制
├── TECH_NOTE.md       # 一页技术说明（§4.3，四个小节）
├── package.json
├── src/               # 前端（浏览器内推理）
├── server/            # Node 纯传输层
├── bench/             # 评测脚本 + 语料 + 查询集 + 原始测量 JSON
└── docs/              # 截图、录屏、日志
```

**验收对照表（每一条都要有对应证据文件）**

| # | 官方要求 | 证据 |
|---|---|---|
| §3.1-1 | 完整流程：导入 → 向量 → 写 seekdb → 查询 → 展示排序结果 | 录屏 + `walkthrough.md` |
| §3.1-2 | 本地推理，无云端推理 API 调用 | **DevTools Network 录屏**证明无外部推理请求 + 代码 |
| §3.1-3 | INT8/FP16，来源、量化方式、体积对比、质量变化 | `perf-report.md` + 体积表 |
| §3.1-4 | WebGPU 优先，不支持自动降级 WASM，界面明确提示 | 两种环境各一张界面截图（要能看到当前后端） |
| §3.1-5 | 向量/原文/元数据存 seekdb，混合检索在 seekdb 完成 | 直连 seekdb 导出的**行级数据** + 实际调用记录 |
| §3.1-6 | 增量导入，刷新后新内容可检索，集合/会话状态正确 | 增量导入脚本 + 输出 |
| §3.1-7 | 可复现性：按说明能启动应用及数据库并完成上述操作 | README 启动步骤 |
| §3.2 | 压缩比、Recall@K/nDCG@K、分阶段计时、中位数、WebGPU/WASM 两套环境 | `bench/` 原始 JSON + 汇总表 |

**所有"已验证"的结论都要写清楚是怎么验证的。**

## 10. 参考资料（可选）

- `ob-labs/mine-kb`（GitHub，39 stars）—— "A local personal knowledge base on SeekDB"，Tauri + React + Vite 的 SeekDB 知识库实现。**可参考它的表结构与索引配置**；但它是桌面应用且用云端 embedding，**不要照抄它的推理路径**。
- 官方文档：https://www.oceanbase.ai/docs/seekdb-js-get-started

## 11. 汇报格式

做完（或阶段性做完）后，用中文回复，包含：

1. **状态**：已完成到哪一步、还在做哪一步。
2. **实际验证结果**：跑过的检查逐条列出 PASS/FAIL，附真实输出摘要（不是"应该能跑"）。
3. **实测数据**：模型体积、压缩比、各阶段延迟（中位数）、Recall@K/nDCG@K —— **全部来自真实运行**。
4. **产出文件清单**：路径 + 一句话说明。
5. **分支与 commit**：分支名 + 完整 40 位 SHA + `git ls-remote` 核对结果。
6. **剩余风险与阻塞**：需要用户做的事（如模型下载被墙、需要截图等），写清楚**用户要做的最小操作步骤**。

**分阶段推进**：每完成一个阶段就 commit 一次并推送，commit message 用英文、说明做了什么和为什么。遇到需要用户本人操作的环节（登录、验证码、付费、授权），**明确列出用户要做的最小步骤，然后继续做其他不依赖该步骤的工作**，不要停下来等。

=== 提示词结束 ===
