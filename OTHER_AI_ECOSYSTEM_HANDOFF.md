# 给另一台电脑上 AI 的任务交接：OceanBase 初赛生态方向

你接手的是能与当前主 AI 同时推进的生态任务。用户希望直接做实际工作，详细保存结果，不需要重新讲基础课或反复询问常规方案。需要本人验证码、账号条款或安全权限确认时，停在具体步骤并继续可独立完成的工作。

本文件及所列 GitHub 分支足以开始工作，不需要访问原电脑的磁盘、WSL、数据库或会话记录。账号登录及新的运行环境需要在你所在电脑或云端准备。

## 1. 双方职责

| 负责方 | 工作 | 主要交付位置 |
| --- | --- | --- |
| 当前主 AI | PowerContext 核心实现、Pi/数量触发/混合检索等分支整合、回归审查、后续证据选择与来源生命周期 | `competition/prelim-integration` 及相应核心任务分支 |
| 你，另一台电脑的 AI | 优先完成高德 Skill 的可交付验证与提交准备、魔搭 Skill 分享；条件允许再完成一个独立 Dify 作品 | 从 `competition/nearby-skill` 新建自己的生态分支 |

两边可以并行。你负责的文件主要放在 `gaode/`、`dify/`；魔搭的作品记录可放 `modelscope/`。主 AI 负责产品 `src/powercontext/`、核心测试、运行时和存储层。遇到产品缺陷，提供最小复现和具体需求给用户转交主 AI，不在生态分支顺便改核心实现。

你无需处理原电脑的 seekdb 实例、遥测编号、端口、代理、用户密码或本地数据库迁移，这些工作暂时留在原侧。

## 2. 项目与官方入口

- 参赛私有仓库：<https://github.com/Icsya05/powercontext>
- seekdb 私有仓库：<https://github.com/Icsya05/seekdb>，本次生态工作优先使用前一个仓库。
- 官方赛题总览：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ocqe6xv6mlgapq24>
- 官方 GitHub 配置：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qs1povt8zbza6hts>
- 官方提测指南：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/ut82q2fcalep4y1r>
- 官方仓库/分支说明：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/brxxufkegusa86hl>
- 高德题面：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/qp60miwsbk1mcgod>
- 魔搭题面：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/bt7u0qwwz84gt48g>
- Dify 题面：<https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lhfslihtnnb8yqh6>
- 官方提测平台：<https://open.oceanbase.com/train/detail/21>
- 赞助 Token 领取说明：<https://ask.oceanbase.com/t/topic/35653137>

已知初赛区间为北京时间 2026-10-26 10:00 至 11-18 24:00，实际截止与提交字段以平台最新页面为准。部分文档的总题数、分值文字不一致；以最新题面及平台为准，不推算或编造已得分。

## 3. 在另一台电脑开始

私有仓库需要用户自己的 GitHub 账号在新环境拥有读取权限。使用该环境正常的 GitHub 登录/授权流程；本交接文件没有密码、Token 或 API Key。

```bash
git clone https://github.com/Icsya05/powercontext.git
cd powercontext
git fetch origin
git switch -c ecosystem/gaode-modelscope origin/competition/nearby-skill
git status --short
```

分支名 `ecosystem/gaode-modelscope` 是本次分工建议；已存在时先检查是否属于本任务，再复用或新建不冲突的名字。阅读该分支内适用的 `AGENTS.md`、协作说明和许可。生态官方基线为 `oceanbase/powercontext:2026-competition-ecosystem`，已有高德分支从该基线开始。

已有高德分支：`competition/nearby-skill`，已推送并核对的 commit：

```text
9ce99250bd92e4dd0aa2d124c0fb649619b4a408
```

先阅读：

- `gaode/SKILL.md`：已有完整单文件 Skill，可作为提交产物。
- `gaode/VALIDATION.md`：真实记录了格式检查及独立场景测试，明确尚无在线高德评测。

你可以直接从上面已保存的实现继续，不必重写一个相同 Skill。原始分支代码链接：

<https://github.com/Icsya05/powercontext/blob/competition/nearby-skill/gaode/SKILL.md>

## 4. 第一优先级：高德「周边去哪儿」

### 目标与已有状态

赛题要求一个基于真实高德地点搜索和步行路线的周边推荐 Skill，提交文件仅 `SKILL.md`。平台提供 Agent、模型、高德工具配置，不要求另装 seekdb、PowerContext、长期记忆服务或独立网站。

已有 Skill 格式检查通过，四个独立 AI 的合成工具场景通过。验证覆盖 901 秒不能算作 15 分钟内、真实步行距离排序、POI 去重、同一起点、缺失地址、部分路线失败、工具错误中的外部指令，以及无法核实营业/安静硬性条件时不假装满足。

这些是行为模拟，尚未发起真实高德请求，也没有平台成绩。

### 你要完成的工作

1. 阅读最新官方题面，核对单文件 Skill 的格式及上传字段。
2. 若当前环境有真实高德 MCP，按实际工具 schema 做地点搜索和步行路线验证；记录实际数据、响应单位、是否发生工具失败。没有工具时保留已完成的离线验证，并把真实验收留给提供工具的官方平台。
3. 核对以下核心要求：
   - 输入是城市、明确起点坐标、自然语言需求。
   - 最多推荐 3 个，用户指定更少时遵守更小数量。
   - 每个地点都是从同一起点出发的独立备选。
   - 步行耗时来自步行路线，按未舍入秒值比较上限；不用搜索距离、直线距离或估速替代。
   - 地点类型、数量、时间等硬条件先满足，再按偏好排序。
   - 每条提供名称、地址、实际步行距离、预计耗时和一句有数据依据的理由。
   - 地址/营业/安静等信息缺失时如实说明；结果不足、无结果和服务失败分别处理。
4. 修改只针对真实发现的问题；保留简短、可核对的测试记录。高德题无需额外交付应用、源码测试框架、录屏或原始 JSON。
5. 准备好最终 `gaode/SKILL.md`。平台可访问且登录、权限齐备时，按实际入口提交。只取得上传文件并不等于成功提交。

### 完成标准

文件能被平台加载；实际提交记录或成绩可核对。若提交被账号、验证码或平台故障阻塞，交付最终文件、已验证行为和具体卡点，不能宣称得分。

参考：[高德 MCP](https://lbs.amap.com/api/mcp-server/summary)、[步行路线字段](https://developer.amap.com/api/webservice/guide/api/direction)。以运行环境实际 schema 为准。

## 5. 第二优先级：魔搭社区分享自己的 Skill

赛题核心是将自己的 Skill 真实上传到魔搭社区，再向比赛平台提交该作品的完整网址或编号。个人主页、账号 ID、Skill 名称均不能代替作品链接/编号。

可优先复用本团队已经编写的高德 Skill，核对魔搭当前上传规范及作品授权后发布。若平台要求额外文件，仅补齐必需的名称、用途、使用示例、工具前提和许可信息，不把账号凭据写进包。

步骤：

1. 使用用户授权的魔搭账号登录；需要注册、验证码、条款或新的敏感授权时，停在具体确认点由本人处理。
2. 查看魔搭当前官方 Skill 上传说明，确认上传结构、可见性与许可。需要公开的作品只包含获授权发布的 Skill 文件和说明，不把整个私有参赛仓库公开。
3. 上传后重新打开作品页，确认能看到正确 Skill 内容；记录完整网址或编号。
4. 在大赛魔搭题入口提交该网址或编号，核对保存结果。
5. 在你自己的分支保存作品说明、最终链接/编号、提交记录及真实状态；清楚区分“已准备”“已上传”“已提测”。

不得伪造账号、上传记录、作品 URL 或成绩。截图可以辅助核对，作品页面本身才是定位依据。

## 6. 第三优先级：独立 Dify 作品（前两项就绪且具备运行条件再做）

这个方向可以与核心代码并行。官方要求使用 Dify 承担核心流程，并实际使用 seekdb 或 PowerContext 至少一种；不要求两种都用。材料放在 `dify/`，基于官方生态分支开发。

建议做一个范围小、可重复体验的互动剧情作品：用户的选择改变后续剧情，PowerContext 保存并在新会话中复用角色/剧情状态。此建议是选题起点，交付以真实运行的作品为准。

独立实现方式：

- 在自己的新环境部署固定版本 PowerContext 或 seekdb，用稳定公开接口接入；不要依赖原电脑的服务地址或数据库内容。
- Dify 负责输入、模型调用/检索/工具请求、条件和结果输出，提交可导入的 DSL。
- 根据当前官方 Dify 文档选兼容版本，核对 HTTP Request 节点、DSL 导入格式、插件及服务网络条件，实际导入并运行验证。
- 模型服务通过环境变量或用户在当地配置提供。配置示例保留占位值。需要购买服务或产生费用时先说明具体方案与费用，不自行开通付费订阅。
- 用两次或新会话中的实际交互证明记忆保存和复用。仅安装组件、测试连接或在文档中写技术名不满足要求。

必须交付：全部 DSL、实际依赖版本、配置/启动/初始化步骤、至少一组完整验证样例、复现或重置方法、真实运行记录。按依赖附配套源码、插件安装包或数据初始化脚本，并注明开源来源与许可。没有真实运行时，按未完成原型交接。

推荐在自己的分支用独立提交实现 Dify；提交或 PR 面向生态分支，不合并到核心产品分支。不要虚构用户反馈、使用人数、提效数据或模型调用记录。

## 7. 其他生态方向的依赖

这些不是本轮并行任务的首选，可在前面完成后再与用户确定是否继续：

- Qoder：主要开发必须真实在 Qoder 中进行，网站必须由 Qoder Sites 发布，并保留账号 UID 和开发记录。用其他 AI 写完再声称 Qoder 开发不符合要求。
- MiniMax：必须真实参与一次代码修改；seekdb/OceanBase 查询资料、PowerContext 状态写入与重启复用都要有证据。
- 阶跃：浏览器本地开源 embedding、INT8/FP16、WebGPU 优先及 WASM 降级、seekdb-js 和数据库内混合检索，需实际应用和实测记录。
- AMD：需 AMD GPU/hipVS 实际参与 HNSW 构建，并做端到端构建计时及 Recall；独立 GPU 查询演示不能代替。

这些方向需要对应工具、账号或硬件条件，不应用通用演示代码冒充已完成。

## 8. 核心侧状态，仅供避免重复

仓库默认 `master` 不包含本轮比赛实现。核心题基于冻结 PowerContext commit `9db1753434162c0aa7c9f1189a1722e617880a52`；不能合并最新上游 master 来替代解题。

| 分支 | 固定检查点 | 实际状态 |
| --- | --- | --- |
| `competition/csv-row-evidence` | `8e9a4bc667f894ba2d7ade133c9b80e01f2b7234` | 原有 CSV/PDF/HTTP 重排/Embedding/增量上下文五题，55 项公开、172 项相关回归通过，已独立审查 |
| `competition/pi-session-evidence` | `8cef331b6faadd3631c1499a99957981c824b570` | 加入 Pi 完整会话/断点；15 项官方、31 项来源与连接器回归通过，独立审查待汇总 |
| `competition/count-trigger` | `dcecf8864d9a3aa72a49ce7fe3cb1d4c83a12044` | 17 项官方、95 项相关回归通过；Linux 原生磁盘运行，挂载盘曾超时；详见分支 HANDOFF |
| `competition/hybrid-single-sql` | `8520dbe876212b2d0a151c84aaeade22f681edab` | 1 项真实后端公开、94 项回归通过/15 skip，EXPLAIN 双索引，完整质量/延迟未测 |
| `competition/prelim-integration` | `eddefeaffe1ebfb3aaa00d657cd0f4255b6a3f6b` | 已整合上述 Pi、数量触发、混合检索；合并后整体验证和独立审查由主 AI 负责 |
| `competition/source-lifecycle` | `6a05bee0b212e619bf7e5e4cbd2255c73f1a9b6f` | WIP，4 项公开通过，但有 19 项 Ruff 待处理，缺少失败重试回归/类型检查；未并入集成分支 |

“按查询和预算选择原文证据”只运行了缺少接口的基线失败测试，尚未实现。核心平台私有仓库读取权限、完整隐藏质量门槛和正式成绩均未确认。

以上状态是接手时的记录。先 `git fetch` 和读取主 AI 后续说明，再决定是否需要检查新提交；不把旧 SHA 当成永远最新。

## 9. 新环境与验证原则

高德/魔搭单文件任务不需要迁移任何本地运行环境。Dify 等独立作品按自身运行说明在新电脑或云端搭建即可。

若你为了接入而需要运行核心产品自测，官方环境是 Linux x86_64、Python 3.12、固定 `competition/requirements.txt`，按 `competition/README.md` 准备。在 Linux 文件系统克隆，避免 Windows 自动换行影响已固定 SHA-256 的样例，也避免 `/mnt/c` 的导入/数据库 I/O 开销触发原生 worker 超时。

```bash
make -C competition install
make -C competition check-baseline
# 只运行与你正在验证的能力相关的官方命令；不要修改题面/测试/依赖/评分资产。
```

固定比赛依赖不等于全仓开发环境。此前全仓 pytest 因缺少 fastapi、fastmcp、platformdirs、typer、langchain_core 等可选依赖出现 110 个收集错误，不能声称全仓测试通过；需要时另建开发环境，保留固定比赛环境。

本交接没有附凭据。GitHub 读仓库 Token 与赞助模型 Token 用途不同；只向实际对应的平台配置所需权限，不在 URL、代码、提交记录或交接材料中暴露真实值。

## 10. 给用户的最终回报格式

每项写清：

1. 做成了什么，实际仓库/分支/完整 SHA。
2. 最终文件或作品页面链接；魔搭必须给作品 URL/编号，高德必须给最终 SKILL.md。
3. 哪些是真实在线运行，哪些仅是模拟或格式检查；实际执行的验证与结果。
4. 哪些已上传、已提测、已取得正式反馈，哪些还没有。
5. 剩余卡点和本人要做的最少操作；无需用户处理的部分直接完成。

保留明确的交接记录。完成一个任务即可提供该项可核对结果，不要把无平台成绩写成“已经拿分”。
