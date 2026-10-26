# wyd 专属交接：高德 Skill 与魔搭发布

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
git switch -c ecosystem/wyd-gaode-modelscope origin/competition/nearby-skill
git status --short
```

同名分支已存在时先检查是否是自己的进度，再切换或续用，不重置它。已保存的起点为 `competition/nearby-skill`，commit `9ce99250bd92e4dd0aa2d124c0fb649619b4a408`。阅读 `gaode/SKILL.md` 和 `gaode/VALIDATION.md`；现有实现可直接继续，不必重写。已有四个合成场景验证，尚无真实高德请求、正式提交或平台成绩。

先完成高德文件和必要验证，再将自己拥有发布权的 Skill 上传魔搭。这两项复用同一作品，安排给你一起完成。无需安装数据库或 Dify，也无需等待 zyj。你不负责 Dify；完成两项后先交付结果，不自行接管 zyj 的目录。

参考文件：https://github.com/Icsya05/powercontext/blob/competition/nearby-skill/gaode/SKILL.md

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


## 任务一：高德「周边去哪儿」

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


## 任务二：魔搭发布与比赛链接提交

赛题核心是将自己的 Skill 真实上传到魔搭社区，再向比赛平台提交该作品的完整网址或编号。个人主页、账号 ID、Skill 名称均不能代替作品链接/编号。

可优先复用本团队已经编写的高德 Skill，核对魔搭当前上传规范及作品授权后发布。若平台要求额外文件，仅补齐必需的名称、用途、使用示例、工具前提和许可信息，不把账号凭据写进包。

步骤：

1. 使用用户授权的魔搭账号登录；需要注册、验证码、条款或新的敏感授权时，停在具体确认点由本人处理。
2. 查看魔搭当前官方 Skill 上传说明，确认上传结构、可见性与许可。需要公开的作品只包含获授权发布的 Skill 文件和说明，不把整个私有参赛仓库公开。
3. 上传后重新打开作品页，确认能看到正确 Skill 内容；记录完整网址或编号。
4. 在大赛魔搭题入口提交该网址或编号，核对保存结果。
5. 在你自己的分支保存作品说明、最终链接/编号、提交记录及真实状态；清楚区分“已准备”“已上传”“已提测”。

不得伪造账号、上传记录、作品 URL 或成绩。截图可以辅助核对，作品页面本身才是定位依据。


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

- `gaode/SKILL.md` 最终文件及真实验证记录，标明模拟与在线运行的区别。
- `modelscope/README.md`：作品完整网址或编号、公开文件范围、许可、使用示例、上传及比赛提交状态。
- `gaode/HANDOFF_WYD.md`：分支、完整 commit SHA、已完成事项、实际检查结果、剩余卡点。
- 推送自己的分支，向团队提供上述链接；账号阻塞时也先交付完整可用文件。

不要等 Dify，也不要代 zyj 提交 Dify。高德和魔搭材料不应依赖 zyj 的地址、账号或成果。
