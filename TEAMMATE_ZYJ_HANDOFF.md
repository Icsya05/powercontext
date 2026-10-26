# zyj 专属交接：独立 Dify 作品

你是队友本人使用的 AI。本说明可以单独使用，不需要原电脑、原聊天记录、WSL 或数据库。用户希望直接完成实际工作并保留可复现材料。遇到必须由账号本人处理的登录、验证码或授权，记录具体卡点，继续其他可完成工作，不索取聊天中的密码或 Token。

这是任务分配，不代表平台已提交或已得分。开始前读取适用的 AGENTS.md 和官方最新题面；本文件中的验证状态截至 2026-10-26。以下分支隔离安排是团队协作约定。

| 人员 | 独立任务 | 分支 | 文件归属 |
| --- | --- | --- | --- |
| wyd | 高德周边推荐 Skill、魔搭发布同一 Skill | `ecosystem/wyd-gaode-modelscope` | `gaode/`、`modelscope/` |
| zyj | 独立 Dify 作品、自己的 seekdb 服务、DSL 和实测 | `ecosystem/zyj-dify` | `dify/` |
| 主 AI | 核心代码整合、回归、证据选择与生命周期后续工作 | `competition/prelim-integration` 等核心分支 | `src/powercontext/`、核心测试 |

两位队友可以立即同时开始，不等待对方，也不共用数据库、模型密钥或本地端口。不要改另一个人的目录、共享根文件、CI、分支保护或核心源代码；需要修改时先给出具体需求。只提交自己负责的文件，不直接推 master，不强推、不改写其他人的历史。PR 如需创建，面向团队生态分支并写清差异；不要把整个生态基线合并进核心分支。分支可作为独立交付，最终合并和比赛填报由团队统一核对，避免覆盖同一题目的提交。

仓库是私有的，先确认本人 GitHub 账号已获协作者权限。不需要把整个仓库改为公开；公开发布仅包含获授权的作品与必要说明，不包含私有代码、个人信息或密钥。

## 开始工作

```bash
git clone https://github.com/Icsya05/powercontext.git
cd powercontext
git fetch origin
git switch -c ecosystem/zyj-dify origin/competition/nearby-skill
git status --short
```

同名分支存在时先检查是否是自己的进度，再续用，不重置。共同起点 `competition/nearby-skill` 的已保存 commit 为 `9ce99250bd92e4dd0aa2d124c0fb649619b4a408`，它来自官方生态基线。`dify/` 目前只有 `.gitkeep`，尚无可运行作品。分支里带有 wyd 的高德初始文件，保留即可，不用修改或依赖它。

你的任务现在是正式的独立分工，不再是“等高德和魔搭做好再选做”。可以立刻与 wyd 同时进行。只在 `dify/` 内保存 DSL、配套服务、部署配置、样例与记录。

## 实现方向与依赖隔离

建议做“能记住选择的互动剧情”：Dify 负责主要交互与模型工作流，你自己部署的 seekdb 实际保存角色、剧情选择与状态，并检索已有状态影响下一轮。题面允许 seekdb 或 PowerContext 至少一种，优先选择独立 seekdb 方案，减少对尚在整合的 PowerContext 代码的依赖。这是团队给你的实现建议，先核对最新题面，细节由你落地。

若 Dify 无法直接连接数据库，在 `dify/service/` 实现最小 HTTP 服务，由 Dify 的 HTTP Request 节点读写真实 seekdb；这仍必须是可复现的真实数据库操作。先核对 seekdb 官方接口和 Dify 当前节点/DSL 文档，不凭记忆猜配置。

最低体验：用户使用独立玩家标识开始剧情、做出选择，状态落入 seekdb；新会话使用同一标识时真实读取上次状态并继续。两个玩家标识要隔离，重置操作要可复现。不能仅依赖 Dify 当前会话变量，也不能把演示结果写死。测试断开数据库时的错误反馈，证明实际依赖链路。

服务地址、模型提供商及密钥都在本机或自己的云环境配置，不连接原电脑，不等待主 AI 集成，不依赖高德或魔搭。先用最小链路跑通，再完善叙事和展示；不要为此改 `src/powercontext/`。模型调用和云资源可能收费，使用已授权资源，需新增付费服务时报告具体费用再办理。

## 官方入口与截止时间

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


## Dify 题面要求与交付标准

你与 wyd、主 AI 都可以并行。官方要求使用 Dify 承担核心流程，并实际使用 seekdb 或 PowerContext 至少一种；不要求两种都用。材料放在 `dify/`，基于官方生态分支开发。

建议做一个范围小、可重复体验的互动剧情作品：用户的选择改变后续剧情，seekdb 保存并在新会话中复用角色/剧情状态。此建议是选题起点，交付以真实运行的作品为准。

独立实现方式：

- 在自己的新环境部署固定版本 PowerContext 或 seekdb，用稳定公开接口接入；不要依赖原电脑的服务地址或数据库内容。
- Dify 负责输入、模型调用/检索/工具请求、条件和结果输出，提交可导入的 DSL。
- 根据当前官方 Dify 文档选兼容版本，核对 HTTP Request 节点、DSL 导入格式、插件及服务网络条件，实际导入并运行验证。
- 模型服务通过环境变量或用户在当地配置提供。配置示例保留占位值。需要购买服务或产生费用时先说明具体方案与费用，不自行开通付费订阅。
- 用两次或新会话中的实际交互证明记忆保存和复用。仅安装组件、测试连接或在文档中写技术名不满足要求。

必须交付：全部 DSL、实际依赖版本、配置/启动/初始化步骤、至少一组完整验证样例、复现或重置方法、真实运行记录。按依赖附配套源码、插件安装包或数据初始化脚本，并注明开源来源与许可。没有真实运行时，按未完成原型交接。

推荐在自己的分支用独立提交实现 Dify；提交或 PR 面向生态分支，不合并到核心产品分支。不要虚构用户反馈、使用人数、提效数据或模型调用记录。


## 工作顺序与建议文件布局

1. 阅读最新 Dify 官方赛题及提测指南，列出必须的作品材料和当前账号/环境条件。
2. 在自己的电脑或云端准备可运行 Dify、seekdb 与模型配置，固定实际版本；模型密钥用占位配置说明。
3. 做通一次“输入 → 读状态 → 生成剧情 → 存状态 → 输出”，实际检查数据库记录。
4. 验证新会话恢复、不同玩家隔离、重置、数据库不可用；记录输入、输出和持久化证据。
5. 导出 DSL，在干净的新 Dify 应用中重新导入运行，核对插件依赖、凭据和外部地址，修复不可移植项。
6. 准备材料和最终可运行作品，具备授权及平台条件时提交本题；记录真实提交状态，未运行或未提交就如实标注。

建议目录（按实际实现调整，不创建空壳文件冒充完成）：

```text
dify/
  README.md             # 作品、架构、实际版本、从零启动与导入步骤
  workflow.yml          # 实际导出且导入验证过的 DSL
  service/              # 必要时提供真实读写 seekdb 的服务源码
  deploy/               # 部署、建库/初始化、重置脚本
  .env.example          # 只有占位值，无真实凭据
  examples/             # 样例输入、完整预期行为和复现步骤
  validation/           # 真实运行记录；截图、脱敏日志按需保存
  HANDOFF_ZYJ.md        # 分支、完整 SHA、验证、提交状态与卡点
```

README 必须说明 Dify 在哪一步承担核心流程，seekdb 在哪一步实际存储和检索；交付验证过的源码、DSL、必要配置和初始化步骤。不要把装好了组件或连接成功当成作品完成。没有真实运行时，交付状态写“原型未完成”。

## 新环境与验证原则

高德/魔搭单文件任务不需要迁移任何本地运行环境。Dify 等独立作品按自身运行说明在新电脑或云端搭建即可。

若你为了接入而需要运行核心产品自测，官方环境是 Linux x86_64、Python 3.12、固定 `competition/requirements.txt`，按 `competition/README.md` 准备。在 Linux 文件系统克隆，避免 Windows 自动换行影响已固定 SHA-256 的样例，也避免 `/mnt/c` 的导入/数据库 I/O 开销触发原生 worker 超时。

```bash
make -C competition install
make -C competition check-baseline
# 只运行与你正在验证的能力相关的官方命令；不要修改题面/测试/依赖/评分资产。
```

固定比赛依赖不等于全仓开发环境。此前全仓 pytest 因缺少 fastapi、fastmcp、platformdirs、typer、langchain_core 等可选依赖出现 110 个收集错误，不能声称全仓测试通过；需要时另建开发环境，保留固定比赛环境。

本交接没有附凭据。GitHub 读仓库 Token 与赞助模型 Token 用途不同；只向实际对应的平台配置所需权限，不在 URL、代码、提交记录或交接材料中暴露真实值。


## 交付给团队的报告

每项写清：

1. 做成了什么，实际仓库/分支/完整 SHA。
2. 最终文件或作品页面链接；魔搭必须给作品 URL/编号，高德必须给最终 SKILL.md。
3. 哪些是真实在线运行，哪些仅是模拟或格式检查；实际执行的验证与结果。
4. 哪些已上传、已提测、已取得正式反馈，哪些还没有。
5. 剩余卡点和本人要做的最少操作；无需用户处理的部分直接完成。

保留明确的交接记录。完成一个任务即可提供该项可核对结果，不要把无平台成绩写成“已经拿分”。

## 你的最终交付清单

- 可导入、实际运行过的 Dify DSL 和配套完整文件。
- 实际依赖版本、部署与配置步骤、示例、重置办法和数据隔离说明。
- 至少一组完整运行记录，证明 seekdb 真实保存状态并在新会话读取复用。
- `dify/HANDOFF_ZYJ.md`，注明已准备、已运行、已提交、平台反馈分别是什么状态。
- 推送自己的分支并提供完整 SHA；交付时不包含真实密钥或个人数据。

高德和魔搭由 wyd 负责；不要等待或修改他的任务。核心产品缺陷提供复现给团队处理，不在本分支改核心代码。
