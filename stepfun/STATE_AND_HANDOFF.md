# 阶跃星辰赛题 —— 状态与交接报告

> 作者：zyj（MiniMax 会话）　｜　日期：2026-10-28 23:2x　｜　状态：**只做了调研与验证，尚未开始实现**
>
> 这份报告接在 `HANDOFF_ZYJ.md`（前一个会话写的赛题解读）与 `AGENT_PROMPT.md`（可直接粘贴的提示词）之后。
> 前两份文档回答「这题要做什么」；本份回答「**现在到哪一步了、哪些结论已经被真实验证过、还有哪些是未验证的假设**」。

---

## 0. 一句话状态

- ✅ 官方赛题原文已逐条读过（2309 字），**§3.1 七项验收、§3.2 六项测量要求、§4 三项提交材料**已抄成对照表。
- ✅ 环境已就绪：seekdb 容器在跑、Node/npm 齐、模型有 fp32/fp16/q8 三套 ONNX。
- ✅ 四个关键 npm 包的真实版本已查实；**新发现一个前一个会话没提到的坑：npm 装不上，必须用 pnpm**。
- ❌ **一行应用代码都还没写。** 没有 `src/`、没有 `server/`、没有 `bench/`、没有页面。
- ⚠️ 前一个会话（"stepfun赛题交接"）**只写了交接文档就停了**，没有实现；它留下的 `HANDOFF_ZYJ.md` 与 `AGENT_PROMPT.md` 是可用的。

---

## 1. 官方题面（已亲自核过，不是转述）

**出处**：语雀《阶跃星辰》，2026-10-26 更新，共 **2309 字**
`https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9`

> 项目：seekdb × 阶跃星辰
> 题目：**端侧 AI 推理性能优化与 seekdb 混合检索**
> 任务：构建一个在浏览器本地完成向量化、使用 seekdb 进行语义与混合检索的迷你知识库应用
> 模型要求：自选可公开获取的开源 embedding 模型，**不限定使用阶跃星辰模型**
> 提交产物：可运行的 Web 应用、完整源码和一页技术说明　｜　总分 20

### 1.1 硬性条款（原文要点）

| 条款 | 要求 |
|---|---|
| §2.2.1 端侧推理 | 用 Transformers.js、ONNX Runtime Web 等端侧运行时，在**用户设备的浏览器中**执行 embedding 推理；**文档向量化和查询向量化均须在本地完成** |
| §2.2.2 模型 | 可自由选择（all-MiniLM-L6-v2、bge-small 等），但**必须为可公开获取的开源模型**，技术说明中注明来源与版本 |
| §2.2.3 量化 | 采用 **INT8 或 FP16** 方案，说明处理方式，报告量化前后的**模型体积、压缩比及检索质量变化** |
| §2.2.4 后端 | **优先 WebGPU**，显式配置推理后端；不支持时**自动降级到 WASM**，并在界面**明确提示当前后端** |
| §2.3.1 接入 | 通过 seekdb-js 接入 seekdb，建集合存向量、原文、文档 ID 等元数据；可嵌入式或本地 server |
| §2.3.2 混合检索 | 检索处理**由 seekdb 完成**，**不得在客户端分别获取两路结果后自行拼合** |
| §2.3.3 写入与刷新 | 正确处理数据写入和索引刷新，确保新导入文档刷新后可检索 |
| §2.3.4 增量与状态 | 管理知识库的增量写入、集合与会话状态，连续导入和切换后结果与当前知识库一致 |
| §2.4 性能优化 | 围绕 embedding 批处理、模型加载、推理延迟、数据库检索延迟、索引刷新策略做优化，**并提供优化前后的实测结果** |
| §2.5 通用红线 | 禁止调用云端推理 API；禁止服务端预计算向量/检索结果后回放；**向量和文档的存储、检索必须使用 seekdb**，不得用其他数据库或客户端内存检索替代 |
| §2.5 浏览器 | Chrome / Edge 最新版 |

### 1.2 §3.1 功能与质量 —— 七项验收（逐项可核）

| # | 检查项 | 通过条件 |
|---|---|---|
| 1 | 完整流程 | 可导入文本、生成向量、写入 seekdb、输入查询并展示排序后的检索结果 |
| 2 | 本地推理 | 文档与查询的 embedding 均在浏览器本地计算，**无云端推理 API 调用** |
| 3 | 模型量化 | 使用 INT8 或 FP16 方案，提供模型来源、量化方式、体积对比及质量变化 |
| 4 | 后端与降级 | 支持时优先 WebGPU；不支持时自动降级至 WASM 并明确提示，核心流程仍可运行 |
| 5 | seekdb 数据层 | 向量、原文及元数据存于 seekdb，向量与全文混合检索**在 seekdb 中完成** |
| 6 | 状态与刷新 | 支持增量导入，索引刷新后新增内容可检索，集合与会话状态正确 |
| 7 | 可复现性 | 按提交的说明可启动应用及数据库，并完成上述操作 |

> 原文明确：「调用云端推理 API、回放服务端预计算结果，或绕过 seekdb 完成存储与检索，均不符合本题要求。」

### 1.3 §3.2 性能与质量测试方法 —— 六项（**这部分的报告工作量最大**）

| # | 要求 |
|---|---|
| 1 | **固定测试条件**：相同设备、浏览器版本、语料和查询集；记录模型版本、精度、推理后端、批大小、seekdb 配置 |
| 2 | **对比模型体积**：同一口径统计实际模型文件总体积，量化前后分别记录，**压缩比 = 量化前体积 / 量化后体积** |
| 3 | **检查检索质量**：同一评测集对比量化前后，注明评测方法；可用 **Recall@K、nDCG@K**，说明变化幅度，避免仅凭主观判断 |
| 4 | **分阶段计时**：分别记录**模型下载与加载、文档向量化、写入与索引刷新、查询向量化、seekdb 检索**，并报告端到端延迟 |
| 5 | **区分首次与后续请求**：首次加载与预热后分开报告；重复测试**保留原始数据并报告中位数**，不能只选最快一次 |
| 6 | **验证降级路径**：分别测试 WebGPU 可用与不可用的环境，确认后端选择、界面提示及 WASM 下的检索流程 |

**题面建议的结果表**（三行 × 五列，必须都有实测值）：

| 配置 | 模型体积 | 向量化吞吐 | seekdb 检索延迟 | 端到端查询延迟 | 检索质量 |
|---|---|---|---|---|---|
| 量化前基线 | 实测 | 实测 | 实测 | 实测 | 指标与结果 |
| INT8 / FP16 + WebGPU | 实测 | 实测 | 实测 | 实测 | 同一指标结果 |
| INT8 / FP16 + WASM | 实测 | 实测 | 实测 | 实测 | 同一指标结果 |

### 1.4 §4 提交材料（三项）

- **4.1 可运行的 Web 应用**：本地可启动；说明浏览器要求、依赖安装与启动步骤；seekdb 用嵌入式或**随应用提供本地 server 的启动脚本与连接配置**；应用要能演示**文档导入、向量化进度、检索结果、当前推理后端**。
- **4.2 完整源码**：应用源码、依赖与配置、**模型获取及量化步骤**、seekdb 集合/表结构与索引配置、**用于复现测试的数据或数据生成方式**。
- **4.3 一页技术说明**：① 模型与量化 ② 端侧运行 ③ seekdb 使用 ④ 状态与优化。

---

## 2. 前一个会话做了什么 / 没做什么

**会话**：`stepfun赛题交接`，session id `mvs_0444507f204e409d94a9cd38d68653fc`（已 idle，用户说它没余额了）。

| 产出 | 状态 |
|---|---|
| `stepfun/HANDOFF_ZYJ.md`（33 KB / 670 行） | ✅ 已提交（commit `21710733`）—— 赛题要点 + 三个坑 + seekdb-js API 速查 + 架构推论 + 环境清单 |
| `stepfun/AGENT_PROMPT.md`（19 KB / 287 行） | ✅ 已提交（commit `0286e646`）—— 可整段粘贴给新 agent 的提示词 |
| `stepfun-seekdb` 容器（28811/28816） | ✅ 起了，还在跑 |
| 应用实现 | ❌ **一行都没有** |
| `src/` `server/` `bench/` `docs/` `package.json` | ❌ 都不存在 |

> 它在最后一轮还专门检查了 `minimax/.gitignore`（那是我这个会话建的），确认自己没误带别人的文件。**它是个规矩的 agent，写的两份文档可以直接用。**

---

## 3. 我这次（MiniMax 会话）做了什么

**做了调研与验证，没有写实现。** 具体动作：

1. 找到并读了前一个会话的 session 记录与两份交接文档。
2. **亲自重读官方赛题原文**（`kw9wfx4bu9pyvat9`，3574 字符），逐条抄出 §2.2/§2.3/§2.5、§3.1 七项、§3.2 六项、§4 三项。
3. **去 npm registry 核了四个包的真实版本**（见 §4.1）。
4. 核了 `stepfun-seekdb` 容器：用 pymysql 以 `root@sys` 连上 `127.0.0.1:28811`，返回 `5.7.25-OceanBase seekdb-v1.4.0.0` ✅
5. 核了 HF 上 `Xenova/all-MiniLM-L6-v2` 的文件清单与各变体真实体积（见 §4.2）。
6. 试装 npm 依赖 → **失败**，并定位了失败原因（见 §5 坑 2）。
7. 试过 `corepack pnpm`（可用）但 `corepack enable` 失败（见 §5 坑 7）。
8. 建过一个 npm 空壳 `package.json`，发现装不上后**已删掉**，仓库现在是干净的。

**没做**：应用代码、浏览器自动化、评测脚本、任何模型下载、任何 seekdb-js 调用。

---

## 4. 已验证的事实（下一位可以直接用）

### 4.1 npm registry（`npm.cmd view` 实测）

| 包 | 版本 | 备注 |
|---|---|---|
| `seekdb` | **1.4.0** ✅ | 这才是真包；`dependencies = { mysql2: '^3.11.5' }`（**干净，无 workspace 依赖**） |
| `@huggingface/transformers` | **4.3.2** ✅ | 依赖：`sharp ^0.35.4`、`onnxruntime-web 1.31.0-dev.20260914-8d85527a0`、`onnxruntime-node 1.30.0`、`@huggingface/jinja ^0.5.10`、`@huggingface/tokenizers ^0.2.0` |
| `@seekdb/bm25` | **1.4.0** ✅ | 依赖：`@types/snowball-stemmers`、`snowball-stemmers` |
| `seekdb-js` | ❌ **404 Unpublished on 2025-12-05T08:30:46Z** | 题面 §2.3.1 写的那个包名**已下架** |

### 4.2 模型文件真实体积（HTTP HEAD 实测，单位字节）

| 精度 | 文件 | 体积 | 压缩比（相对 fp32） |
|---|---|---|---|
| fp32（基线） | `onnx/model.onnx` | **90,387,606**（86.2 MiB） | 1.000× |
| fp16 | `onnx/model_fp16.onnx` | **45,297,825**（43.2 MiB） | **1.996×** |
| q8 / int8 量化 | `onnx/model_quantized.onnx` | **22,972,370**（21.9 MiB） | **3.935×** |
| uint8 | `onnx/model_uint8.onnx` | **22,845,806**（21.8 MiB） | 3.956× |
| int8 | `onnx/model_int8.onnx` | 未测（SSL 抖动，重试可测） | — |

模型仓库：`Xenova/all-MiniLM-L6-v2`
- license **apache-2.0**、`library_name: transformers.js`、`pipeline_tag: feature-extraction`
- 维度 **384**（与 `VectorIndexConfig({ hnsw: { dimension: 384 } })` 对得上）
- 全部 ONNX 变体都有：`model.onnx` / `model_fp16.onnx` / `model_quantized.onnx` / `model_int8.onnx` / `model_uint8.onnx` / `model_q4.onnx` / `model_bnb4.onnx`
- 下载量 4.4M、177 likes
- sha：`751bff37182d3f1213fa05d7196b954e230abad9`

> ✅ **这三套变体直接满足 §2.2.3 的"INT8 或 FP16 + 体积/压缩比对比"**，而且是同一个模型的真实 fp32/fp16/q8，不是两个不同模型。

### 4.3 环境现状（接手即可用）

| 项 | 状态 |
|---|---|
| `stepfun-seekdb` 容器 | ✅ Up，端口 `28811`(MySQL) / `28816`(HTTP)，卷 `stepfun-seekdb-data`，root 密码 `StepFun@2026` |
| `dify-seekdb` 容器 | ✅ Up（healthy），端口 `2881`/`2886` —— **Dify 那条线在用，别动** |
| seekdb 版本 | `5.7.25-OceanBase seekdb-v1.4.0.0` |
| Node | **v24.16.0** |
| npm | 11.x（**必须用 `npm.cmd`**） |
| corepack | 0.35.0；`corepack pnpm` 可用 → **pnpm 12.16.1** |
| Python / git | 3.12.10 / 2.55.0 |
| 浏览器自动化 | **未验证**（Playwright 能不能装、Chromium 能不能下，都还没试） |

### 4.4 架构（沿用前一个会话的推论，逻辑成立）

```
浏览器（Vite + TS + @huggingface/transformers）
  文档向量化 / 查询向量化 都在本地
  device: webgpu → 不支持则 wasm，界面显示当前后端
        ↓ HTTP（只传向量 + 原文，不传模型）
Node 纯传输层（零推理、零排序）
  seekdb-js → collection.add({embeddings}) / collection.hybridSearch()
        ↓ MySQL 协议 28811
seekdb：稠密向量列 + HNSW ｜ 原文列 + ik 全文索引 ｜ BM25 稀疏向量（可选第三路）
```

---

## 5. 踩过的坑（坑 1、3 是前一个会话的，**坑 2 和 7 是本次新发现的**）

| # | 坑 | 后果 | 绕法 |
|---|---|---|---|
| 1 | npm 上 `seekdb-js` 已 unpublish | 题面写的包名装不上 | 用 `seekdb@1.4.0`（源码 `oceanbase/seekdb-js`） |
| **2 🆕** | **`npm install` 报 `EUNSUPPORTEDPROTOCOL: Unsupported URL Type "workspace:"`** | **npm 装不上这个工程** | **必须用 pnpm**（`corepack pnpm install`）。`seekdb` 自己的依赖是干净的，workspace 协议来自它 monorepo 里的兄弟包 |
| 3 | SDK 默认在 Node 端自动算向量 | 直接违反「禁止云端/服务端推理」 | `VectorIndexConfig({ ..., embeddingFunction: null })`；且**不装** `@seekdb/default-embed`/`qwen`/`openai`/`jina`（后三个是云端） |
| 4 | 混合检索客户端拼合 | 基础验收直接不通过 | 用 `collection.hybridSearch({ query, knn, nResults })` 一次调用，排序在 seekdb 内 |
| 5 | 浏览器不能直连 seekdb（mysql2 是 TCP socket，嵌入式要原生模块） | 架构上走不通 | 浏览器 → Node 纯传输层 → seekdb |
| 6 | 2881/2886 已被 Dify 占用 | 端口冲突 | 用 28811/28816；**Windows 必须用命名卷**，不要 bind mount |
| **7 🆕** | **`corepack enable` 报 `EPERM: operation not permitted, mkdir 'D:\'`** | pnpm 的 shim 装不上 | **不要 enable**，直接 `corepack pnpm <cmd>`（已验证可用） |
| 8 | Windows/PowerShell 5.1 | npm 的 `.ps1` 包装器被拦 → 用 `npm.cmd`；`.ps1` 文件必须带 UTF-8 BOM；commit message 用 `UTF8Encoding($false)`；`Remove-Item` 被拦 → 用 `Move-Item` / `git clean -f`；`edit` 工具匹配中文全角标点会失败 → 改用 Python 脚本替换 | 同左 |
| 9 | 端口/HTTP 服务 | `seekdb` SDK 依赖 `mysql2`，**Node >= 20** | Node 24 满足 |
| 10 | 维度 | 默认 384；`bge-small-zh` 是 **512**，用它必须显式 `dimension: 512` | 选 all-MiniLM 就用 384 |

---

## 6. 剩余工作清单（对照官方验收逐条）

### 6.1 §3.1 七项验收 —— 全部还没做

| # | 要做什么 | 难点 |
|---|---|---|
| 1 | 导入文本 → 浏览器向量化 → 写入 seekdb → 查询 → 展示排序结果 | 打通「浏览器 → Node → seekdb」链路 |
| 2 | 证明 embedding 全在浏览器 | 浏览器 Network 日志 + **服务端 package.json 里不得出现任何 embedding 依赖** |
| 3 | INT8/FP16 量化 + 体积对比 + 质量变化 | fp32/fp16/q8 三套变体已备好（§4.2） |
| 4 | WebGPU 优先 + 自动降级 WASM + 界面提示 | 需要一个「强制 WASM」开关，评审可一键验证降级 |
| 5 | 向量/原文/元数据存 seekdb，混合检索在 seekdb 内完成 | `hybridSearch()` 的真实 API **尚未验证** |
| 6 | 增量导入 + 索引刷新后能检索到 + 集合/会话状态 | seekdb-js 的 flush / index refresh API **尚未验证** |
| 7 | 按说明可启动应用与数据库 | README 写清楚启动步骤 |

### 6.2 §3.2 六项测量 —— 需要一整套 bench/

- [ ] 固定测试条件的记录（设备/浏览器/语料/查询集/模型版本/精度/后端/批大小/seekdb 配置）
- [ ] 模型体积对比表（**数据已经量好了**，见 §4.2，但要在正式环境再测一遍并记录口径）
- [ ] 评测集 + 相关性标注 → Recall@K / nDCG@K 脚本
- [ ] 五段计时（模型下载与加载 / 文档向量化 / 写入与索引刷新 / 查询向量化 / seekdb 检索）+ 端到端
- [ ] 首次 vs 预热后分开报，重复 N 次取**中位数**，保留原始 JSON
- [ ] WebGPU 可用 / 不可用两条路径各测一遍
- [ ] 产出题面建议的三行五列表

### 6.3 §4 三项材料

- [ ] `README.md`（浏览器要求、依赖安装、启动、seekdb 连接配置、已知限制）
- [ ] `TECH_NOTE.md`（**一页**：模型与量化 / 端侧运行 / seekdb 使用 / 状态与优化）
- [ ] 源码 + 依赖配置 + 模型获取与量化步骤 + seekdb 表结构与索引配置 + **可复现的语料/查询集生成方式**

---

## 7. 推荐执行路线

| 阶段 | 目标 | 完成判据 |
|---|---|---|
| **0（30 分钟）** | **补验证假设**：装 pnpm；跑一个最小脚本确认 `seekdb@1.4.0` 的 `add({embeddings})` 与 `hybridSearch()` 在 28811 上真的能用；确认 Transformers.js 的 dtype 选项名 | 三条假设都有真实验证输出 |
| **1（半天）** | 端到端最小链路：浏览器 Transformers.js 算 384 维 → Node `add({embeddings})` 写入 → `query({queryEmbeddings})` 查回 | 页面上能查回结果 |
| **2（半天）** | 换成 `Schema`（ik 全文 + hnsw 向量），改用 `hybridSearch()` | **前端只发一次请求、只收一次结果**（这是合规红线） |
| **3（1 天）** | WebGPU/WASM 切换 + 界面显示当前后端 + 「强制 WASM」开关；三套 dtype 的体积对比 | 两个后端各截图，体积表填满 |
| **4（1 天）** | 造语料（100–300 条中文片段）+ 20–50 条查询 + 相关性标注；写 Recall@K/nDCG@K；五段计时跑 20 次取中位数 | §3.2 的三行五列表填满，原始 JSON 落盘 |
| **5（半天）** | `README.md` + `TECH_NOTE.md`（一页）+ 截图/录屏/行级数据 | 材料齐全 |
| **6** | commit + push，汇报**分支名 + 40 位 SHA + `ls-remote` 核对结果** | 远端可拉取 |

**分支纪律**：资产只放 `stepfun/`；不要动 `dify/` `gaode/` `modelscope/` `minimax/` `qoder/`；不许 force push；提测合流由队长做。**建议从官方基线 `d647275c` 切新分支**（不要从 `ecosystem/zyj-dify` 切，那条是含全部资产的提测合流分支）。

---

## 8. 我**没有**验证的假设（下一位必须自己先确认）

| # | 假设 | 来源 | 风险 |
|---|---|---|---|
| 1 | `seekdb@1.4.0` 导出 `Schema` / `VectorIndexConfig` / `FulltextIndexConfig` / `SparseVectorIndexConfig` / `K` | 前一个会话读 README | 中 —— API 名可能对不上 |
| 2 | `collection.hybridSearch({ query, knn, nResults })` 的签名与行为 | 前一个会话读 README | **高** —— 混合检索是合规红线，签名不对要重做 |
| 3 | `@seekdb/bm25` 的 `Bm25EmbeddingFunction` 用法 | 前一个会话读 README | 低（第三路，可选） |
| 4 | Transformers.js 4.3.2 的 dtype 选项名（`fp32`/`fp16`/`q8`/`int8`/`uint8`） | 常识推断 | 中 —— 名字错了就切不了精度 |
| 5 | `seekdb-js` 端到端能装上并连上 28811 | 未验证 | **高** —— `workspace:` 协议要用 pnpm 解决 |
| 6 | 浏览器里能下载 HF 模型（`huggingface.co` 出网 + 代理） | 未验证 | 中 —— 评审环境也要能下 |
| 7 | Playwright / Chromium 能装能跑（做自动化计时与 Network 取证） | 未验证 | 中 —— 装不动就只能手工计时 |
| 8 | 本机浏览器有没有 WebGPU | 未验证 | 中 —— 影响「WebGPU 可用」那行怎么测 |

> **阶段 0 就是专门干这个的。** 先把 1/2/4/5 变成事实，再动手写应用 —— 否则容易写完才发现 API 对不上。

---

## 9. 给下一位的一页速查

```bash
# pnpm（不要用 npm，seekdb 是 pnpm monorepo 发的）
corepack pnpm install
corepack pnpm --version          # 12.16.1

# seekdb 连接（服务端模式，跨平台最稳）
#   host 127.0.0.1  port 28811  user root  password StepFun@2026
#   tenant: 连 OceanBase 才需要；本地 seekdb server 不需要
#   database: 自己建（建议 stepfun_kb）

# 端侧合规三件套
#   1) Schema 里 embeddingFunction: null
#   2) 不装 @seekdb/default-embed / qwen / openai / jina
#   3) Node 服务只做转发：收向量 → 调 seekdb → 原样回传

# 量化：同一个模型的三个真实变体
#   fp32  onnx/model.onnx            90,387,606 B
#   fp16  onnx/model_fp16.onnx       45,297,825 B   1.996x
#   q8    onnx/model_quantized.onnx  22,972,370 B   3.935x

# 浏览器
#   Chrome / Edge 最新版；WebGPU 优先，不支持降级 WASM，界面必须显示当前后端
```

---

## 10. 相关文件索引

| 文件 | 内容 |
|---|---|
| `stepfun/HANDOFF_ZYJ.md` | 前一个会话写的赛题解读 + 三个坑 + seekdb-js API 速查（**先读这个**） |
| `stepfun/AGENT_PROMPT.md` | 可整段粘贴给新 agent 的提示词（287 行） |
| `stepfun/STATE_AND_HANDOFF.md` | **本文件**：已验证事实 / 剩余工作 / 未验证假设 |
| 官方赛题 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/kw9wfx4bu9pyvat9 |
| 提交材料说明 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lhfslihtnnb8yqh6 |
| GitHub 使用说明（PAT/提测） | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts |
| 测评平台 | https://open.oceanbase.com/train/detail/21 |
| seekdb-js 文档 | https://www.oceanbase.ai/docs/seekdb-js-get-started |
| 模型仓库 | https://huggingface.co/Xenova/all-MiniLM-L6-v2 |

---

## 11. 一条纪律提醒

**本仓库有多个 agent 并行在同一个 git 工作目录里干活。** 前一个会话就撞见过 `minimax/.gitignore`
被别的会话创建。规矩：

- 每个会话**只 `git add` 自己那个目录**，**绝不用 `git add .` / `git add -A`**（会抢 `.git/index` 并误带别人的文件）；
- 各自用独立分支；
- 不改写他人历史、不 force push、不推 master。
