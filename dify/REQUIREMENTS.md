# REQUIREMENTS — 2026 OceanBase 大赛 Dify 赛题（zyj 独立作品）

本文件是本任务的**需求基线**：每一条都标注来源，区分「官方明确要求」与「我的实现选择」。
凡是无法核验的内容一律写明状态，不猜测、不伪造。

- 整理时间：2026-10-27
- 负责范围：`dify/` 目录（队友 xjl 负责 `gaode/`、`modelscope/`，本任务不改动其内容）
- 作品：《午夜便利店 · 阿澈会记得你》（暂定名，见 `README.md`）

---

## 1. 已核验的官方来源

| # | 来源 | URL | 读取状态 |
| --- | --- | --- | --- |
| S1 | Dify 赛题（**主依据**） | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lhfslihtnnb8yqh6 | ✅ 已读全文（浏览器渲染，3388 字，更新时间 2026-10-26 11:53） |
| S2 | 算分规则 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/xkmkblbzlzk581ya | ✅ 已读全文 |
| S3 | GitHub 在大赛中的使用说明 | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts | ✅ 已读全文 |
| S4 | 测试（提测入口索引） | https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ut82q2fcalep4y1r | ✅ 已读全文（仅索引页） |
| S5 | 比赛主页 | https://open.oceanbase.com/competition?activityCode=4924143&officerId=4965 | ⚠️ 页面为纯前端渲染，未读取到正文；平台入口已知 |
| S6 | 官方提交平台（Dify 题目录） | https://open.oceanbase.com/train/detail/21 | ⚠️ 需登录，未读取（见 §7） |
| S7 | 官方基线分支 | https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem | ✅ 已读取（GitHub API，commit `d647275c`） |
| S8 | 官方 Dify 插件源码 | `oceanbase/powercontext` @ `integrations/dify/` | ✅ 已读取 README 与目录结构 |
| S9 | 官方 seekdb 镜像说明 | https://github.com/oceanbase/docker-images/blob/main/seekdb/README.md | ✅ 已读全文 |
| S10 | seekdb 官方仓库 | https://github.com/oceanbase/seekdb | ✅ 已克隆 `Icsya05/seekdb` @ `2026-competition`，读取 README_CN 与测试用例 |
| S11 | Dify 1.17.1 DSL 规范 | https://github.com/langgenius/dify/tree/1.17.1 | ✅ 已读取 `api/constants/dsl_version.py` 与 `api/tests/fixtures/workflow/*.yml` |

未能读取的来源：**S5 / S6 需要登录 OceanBase 社区账号**，语雀页面虽可公开阅读但 S4 的
「比赛仓库地址」「判题实效性」两个子页尚未逐一核对（见 §7 的最小操作清单）。

---

## 2. 官方硬性要求（逐条摘自 S1）

### 2.1 基线与提交位置

| 要求 | 原文要点 | 本任务落实 |
| --- | --- | --- |
| R1 | 基于 `oceanbase/powercontext` 的 `2026-competition-ecosystem` 分支开发 | ✅ 官方基线 commit `d647275c308e09b7b623f322a26f5c4e85734fb0`（"chore: initialize 2026 competition ecosystem directories"）已确认；本分支 `ecosystem/zyj-dify` 的祖先包含该提交 |
| R2 | 测评平台提交的分支 / commit hash 必须基于上述分支 | ✅ `ecosystem/zyj-dify` 直接由 `competition/nearby-skill`（其父提交即官方基线 `d647275c`）派生 |
| R3 | 项目资产放入对应的 `dify` 目录 | ✅ 全部产出位于 `dify/` |
| R4 | 导入私有 repo 后会获得同名分支 | ✅ 团队私有仓库 `Icsya05/powercontext`（PRIVATE）即导入后的仓库 |

### 2.2 技术结合要求

| 要求 | 原文要点 | 本任务落实 |
| --- | --- | --- |
| R5 | **必须使用 Dify**，承担核心流程编排（输入处理、模型调用、检索/工具调用、条件判断、结果输出） | ✅ Dify Workflow 承担全部编排；见 `workflow.yml` |
| R6 | **实际使用 seekdb、PowerContext 中至少一种**（可同时使用两者） | ✅ 选择 **seekdb**：承载 NPC 长期记忆（状态表 + 历史对话表 + 中文全文索引），由 HTTP Request 节点经配套后端真实读写 |
| R7 | 指定技术必须在应用功能或部署运行中**实际发挥作用**；仅安装组件或测试连接不满足 | ✅ 每轮对话真实 INSERT / UPDATE / SELECT，并由 seekdb 全文检索召回历史；`validation/` 记录数据库行级证据 |
| R8 | 可通过 HTTP API、自定义工具或配套后端接入；Dify HTTP Request 节点支持调用外部服务 | ✅ 采用「配套后端 + HTTP Request 节点」方式，后端源码在 `dify/service/` |
| R9 | 运行说明需交代实际接入方式、依赖版本与配置步骤 | ✅ `README.md` |
| R10 | 使用插件时注明插件名称与安装来源 | ➖ 本作品未使用插件（官方 `integrations/dify/plugin` 尚未发布到 Dify 插件市场，见 §5） |

### 2.3 基础验收（S1 §3.1）

| 编号 | 要求 | 本任务落实 | 状态 |
| --- | --- | --- | --- |
| A1 | DSL 可导入；模型、插件、数据、后端可按说明配置；应用能接收输入并返回结果 | `workflow.yml` + `README.md` 部署步骤 | 待真实 Dify 验证 |
| A2 | 至少一组完整验证样例：初始条件、输入、操作步骤、预期表现 | `examples/walkthrough.md` + `validation/` | 样例文档已写，待真实运行补证据 |
| A3 | 技术结合有效：可由数据库读写记录、节点执行记录、查询结果核对 | `dify/validation/service_checks.py` + `workflow_checks.py` | 服务侧已实现，真实运行待 Docker |
| A4 | 过程可复现：评审不依赖作者本地未交付的数据 / 配置 / 服务状态 | `deploy/docker-compose.yml` + `.env.example` + 初始化脚本 | 已实现，待真实运行验证 |

### 2.4 提交材料（S1 §4）

| 编号 | 要求 | 对应文件 | 状态 |
| --- | --- | --- | --- |
| M1 | 全部 DSL 文件，说明用途与导入顺序，注明适用 Dify 版本与部署方式 | `workflow.yml`（单文件）、`README.md` | 已实现 |
| M2 | 运行说明：创意/玩法/体验方式、Dify 与指定技术分工 | `README.md` | 已实现 |
| M3 | 运行环境、软件与插件版本、所需模型服务及配置项 | `README.md` + `.env.example` | 已实现 |
| M4 | 从安装依赖 → 导入 DSL → 初始化数据 → 启动应用的完整步骤与应用入口 | `README.md`、`deploy/` | 已实现 |
| M5 | 外部服务获取与配置、Dify 访问服务所需网络条件、资源条件、已知限制 | `README.md` | 已实现 |
| M6 | 配置示例只用占位值，不提交真实 API Key / 密码 | `.env.example`（`YOUR_*` 占位） | ✅ 已遵守 |
| M7 | 复用公开工作流 / 代码 / 数据须注明来源与改动 | `README.md` §来源与许可 | 已实现 |
| M8 | 验证样例：初始状态、输入与顺序、预期交互、实际运行结果与截图/日志证据 | `examples/`、`validation/` | 文档已写，真实证据待补 |
| M9 | 说明 seekdb / PowerContext 在应用功能或部署运行中的作用及对应记录 | `README.md`、`validation/service_checks.md` | 待真实运行 |
| M10 | 涉及 seekdb 部署 Dify 时须补 Dify 版本/适配分支、seekdb 版本、数据库用途、部署配置、初始化方式、实际读写验证步骤 | ➖ 本作品**不**用 seekdb 部署 Dify，而是用 seekdb 作应用数据存储，因此不适用；但仍提供 seekdb 版本、用途、部署配置与读写验证 | 见 `README.md` §seekdb 章节 |
| M11 | 自定义后端：源码、依赖清单、配置示例、启动说明 | `dify/service/`、`dify/deploy/` | 已实现 |

---

## 3. 评分口径（S2）

- 初赛总分 **620 分**，其中生态分 **140 分**。
- 生态分项中 **Dify = 20 分**（与 S1 标题页「总分 20」一致）。
- 同分时提交早者排名靠前 → 早提测有实际价值。
- 排名不看「节点数量 / 插件数量 / 是否同时用了两种指定技术」。

评价维度（S1 §3.2）：创意、趣味与互动、体验与完成度、技术结合、工程质量与可复现性。

> S1 明确写明「具体评分细则、权重由赛事后续公布」，因此以上为当前可核验口径。

---

## 4. 时间线

| 事项 | 日期 | 来源 |
| --- | --- | --- |
| 初赛窗口开始 | 2026-10-26 10:00 | 交接任务书（官方页面未标注，已知范围） |
| 初赛截止 | 2026-11-18 24:00 | 交接任务书 |
| Dify 题面最后更新 | 2026-10-26 11:53 | S1 页面元数据 |
| 官方基线分支建立 | 2026-10-23 | S7 commit `d647275c` |
| seekdb 镜像 1.4.0 发布 | 2026-10-10 | S9 / Docker Hub |

---

## 5. 关键技术选型与理由

### 5.1 为什么用 seekdb 而不是 PowerContext

- S1 允许二选一，且「选择 PowerContext 的作品不额外要求使用 seekdb」。
- 官方 PowerContext Dify 插件（`oceanbase/powercontext` @ `integrations/dify/plugin`）自述
  **「No Workflow/Chatflow DSL templates ship with this plugin」**，且插件尚未进入
  `langgenius/dify-plugins`（追踪 issue #1837），市场不可得；直接使用它无法保证评审可复现。
- seekdb 官方提供 MySQL 协议服务与 `pyseekdb` Python SDK，评审侧复现成本更低。

### 5.2 为什么是「Dify + 配套后端 + seekdb」而不是「seekdb 部署 Dify」

- S1 允许把 seekdb 用作应用数据存储，并明确「Dify 的 HTTP Request 节点支持调用外部服务」。
- 用 seekdb 顶替 Dify 的 PostgreSQL 需要改动 Dify 方言与迁移逻辑（S1 提到「适配分支」时
  需附源码），风险与工期远高于收益，且更容易在评审环境失败。
- 本方案下 seekdb 承担**明确的数据职责**（状态 + 对话历史 + 中文全文检索召回），
  满足 R7 的「实际发挥作用」要求。

### 5.3 固定版本

| 组件 | 版本 | 来源 |
| --- | --- | --- |
| seekdb 服务 | `oceanbase/seekdb:1.4.0-100000172026082615` | Docker Hub（对应 seekdb v1.4.0 发布） |
| seekdb Python SDK（备选/交叉验证） | `pyseekdb==1.4.0.post1` | PyPI |
| Dify | **1.17.1**（commit `8387590ace4a094de812b7847fc6a4c3a27cd52b`） | 官方插件 README 的 CI 固定版本 |
| Dify DSL 版本 | `CURRENT_APP_DSL_VERSION = 0.7.0` | `api/constants/dsl_version.py` @ 1.17.1 |
| Dify 插件守护进程 | `0.6.10`（commit `1310a18b2f6bc6f18768a0a6265484830891433c`） | 官方插件 README |
| Python | 3.12 | 与 Dify 插件运行时一致 |

> 官方插件 README 指出其声明边界为「Dify 1.17.1 + 默认 0.6.10-local 守护进程」。
> 本作品不使用插件，但**仍以 1.17.1 为目标版本**，以保证 DSL 可导入且与官方生态一致。

---

## 6. 需要评审者补齐的外部依赖（作品自身不绑定任何付费服务）

| 依赖 | 说明 | 是否必须 |
| --- | --- | --- |
| Dify 实例 | 1.17.1，自行 docker compose 部署 | 必须 |
| seekdb 实例 | `docker compose -f dify/deploy/docker-compose.yml up -d` | 必须 |
| 模型服务 | 任意 OpenAI 兼容 Chat 模型（OpenAI / DeepSeek / MiniMax / 通义等），在 Dify「模型提供商」中配置 | 必须 |
| Embedding / Rerank | **不需要**：本作品的语义召回用 seekdb 中文全文检索（IK 分词）实现 | 不需要 |

模型服务为唯一可能产生费用的项，由参赛者自行选择；本仓库不内置任何付费密钥。

---

## 7. 必须由本人（账号持有人）完成的最小操作

以下步骤涉及登录、验证码、PAT 或授权，AI 无法代办：

| # | 步骤 | 目的 | 平台 |
| --- | --- | --- | --- |
| U1 | 安装 Docker Desktop（Windows 11 家庭版需 WSL2，安装过程有 UAC 提权与可能的一次重启） | 本机跑起 Dify 与 seekdb，做真实运行与 DSL 导出验证 | 本机 |
| U2 | 登录 OceanBase 社区，进入 Dify 题目录 | 提交作品、填写仓库地址与分支 commit | https://open.oceanbase.com/train/detail/21 |
| U3 | 在 GitHub 为 `Icsya05/powercontext` 生成 PAT（scope: `repo`） | 评测平台需要用带 PAT 的 clone 地址拉取私有仓库（S3 明确要求） | GitHub 设置页 |
| U4 | 把 `https://<user>:<PAT>@github.com/Icsya05/powercontext` 填入参赛信息 | 官方要求 | 提交平台 |
| U5 | 在 Dify 界面配置模型提供商并填入自己的 API Key | 工作流的 LLM 节点需要真实模型 | 本机 Dify |

> PAT 与 API Key **只**填入平台表单或本机 `.env`，不得写入任何提交文件、README、日志或截图。

---

## 8. 当前状态清单

| 项目 | 状态 |
| --- | --- |
| 官方需求核验 | ✅ 已完成（S1–S4、S7–S11 已读；S5/S6 需登录） |
| 队友 xjl 任务边界确认 | ✅ 已完成（`gaode/`、`modelscope/`，分支 `ecosystem/wyd-gaode-modelscope` @ `80a052d7`） |
| 分支建立 | ✅ `ecosystem/zyj-dify`，祖先含官方基线 `d647275c` |
| 记忆服务代码 | ✅ 已实现（`dify/service/`） |
| 错误处理 | ✅ 已实现并**已真实验证**（服务在 seekdb 不可达时返回 `DB_UNAVAILABLE` 与可读中文提示） |
| Dify DSL | ✅ 已编写（`dify/workflow.yml`），**待真实 Dify 导入 / 导出 / 再导入验证** |
| seekdb 真实读写 | ⏳ 待 Docker 就绪后执行 |
| 完整验证样例 | ⏳ 文档已写，真实运行证据待补 |
| 提测 | ❌ 未开始（需 U2–U4） |
| 官方成绩 | ❌ 无（不预��任何分数） |

---

## 9. 与队友任务的边界

- xjl（分支 `ecosystem/wyd-gaode-modelscope`，HEAD `80a052d7`）交付 `gaode/`（SKILL.md、
  VALIDATION.md、7 场景离线回归）与 `modelscope/`（发布脚本、README）。
- 该分支与官方基线之间的差异经 `git diff 9ce99250 80a052d7 --stat` 核对为 **仅 15 个文件、
  全部位于 `gaode/` 与 `modelscope/`**，`dify/` 两侧字节一致（仅 `.gitkeep`）。
- 本任务**不修改** `gaode/`、`modelscope/`、`src/powercontext/`、CI 与根级共享文件；
  改动范围严格限制在 `dify/`。
