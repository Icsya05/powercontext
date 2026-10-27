# 提测清单（Dify 赛题）

> 依据：官方《GitHub 在大赛中的使用说明》、官方《Dify》题面 §4、官方《测试》索引页。
> 提交时间与字段以提交平台页面实际显示为准；本文件是准备清单，不是平台字段的猜测。

---

## 一、提测前必须完成的团队动作：生态分支合流

官方 Dify 题面原文：

> 为方便判题，请基于 `https://github.com/oceanbase/powercontext/tree/2026-competition-ecosystem`，
> 在测评平台提交时的分支 / commit hash 基于此分支进行开发，相关项目资产放入对应 `dify` 目录中。

「相关项目资产放入对应目录」意味着**一条提交分支里应该同时包含各生态方向的资产**。
目前团队的分支拓扑是：

```text
d647275c  官方基线 2026-competition-ecosystem
   └── 9ce99250  competition/nearby-skill                （共同起点）
         ├── ecosystem/zyj-dify                 ← 本任务：dify/
         └── ecosystem/wyd-gaode-modelscope     ← xjl：gaode/ + modelscope/
```

**两条并列分支互不包含**，所以提测前必须先合流：

- 建议由**核心负责人 / 队长**用 PR 把各条 `ecosystem/*` 分支合到一条提交分支
  （例如新建 `competition/ecosystem-submit`），再把这条分支的分支名 + commit hash 填进平台；
- 各人**不要**直接改写他人分支的历史，也不要把别人的目录搬进自己分支冒充自己的工作；
- 合流后请核对：目标分支里 `dify/`、`gaode/`、`modelscope/` 三个目录都在，且内容分别来自各自的分支。

> 待办：合流分支名尚未确定，由队长决定后回填本节。

---

## 二、平台表单需要准备的东西

| # | 需要填的东西 | 本作品的对应物 | 状态 |
| --- | --- | --- | --- |
| 1 | **比赛仓库地址**（必须是带 PAT 的形式，官方明确要求） | `https://<你的GitHub用户名>:<PAT>@github.com/Icsya05/powercontext` | 待生成 PAT |
| 2 | **分支名** | 合流后的提交分支名 | 待合流 |
| 3 | **commit hash** | 合流分支的完整 SHA | 待合流 |
| 4 | **Dify 作品链接**（若表单要求） | Dify 里导入 DSL 后的应用访问链接 / API 地址 | 待真实验证后确定 |
| 5 | **作品说明 / 运行说明** | `dify/README.md` | ✅ 已完成 |
| 6 | **验证样例** | `dify/examples/walkthrough.md` + `dify/validation/` | ✅ 文档已完成，证据待真实运行补齐 |

### PAT 生成步骤（官方《GitHub 在大赛中的使用说明》）

1. GitHub 右上角头像 → **Settings**
2. 左侧最下面 → **Developer settings**
3. **Personal access tokens → Tokens (classic)**
4. **Generate new token (classic)** → 勾选 `repo` scope → 生成
5. **立刻复制保存**（离开页面就看不到了）
6. 填进平台后，用下面这条命令验证能 clone：

```bash
git clone https://<你的GitHub用户名>:<PAT>@github.com/Icsya05/powercontext
```

> PAT **只**填进平台表单，不要写进任何提交文件、README、日志或截图。

---

## 三、提交前自检清单

- [ ] 合流分支里 `dify/`、`gaode/`、`modelscope/` 都在
- [ ] `git ls-remote origin <合流分支>` 返回的 SHA 与填进平台的一致
- [ ] 带 PAT 的 clone 地址能正常 clone
- [ ] `dify/workflow.yml` 是**从真跑过的应用里导出的**那一份（不是手写初稿）
- [ ] `dify/README.md` 里的命令在干净环境按顺序能跑通
- [ ] `dify/validation/` 里有真实运行记录（数据库行、日志、截图）
- [ ] `dify/.env.example` 只有占位值；仓库里没有任何真实 Key / Token / PAT
- [ ] `dify/workflow.yml` 里没有模型凭据（DSL 导出本来就不含凭据，但导入后要重新绑定模型——README §5.7 已写）
- [ ] 作品链接能在**没登录**的浏览器里打开（或确认表单要求的是 API 地址）
- [ ] 完整读一遍 `dify/HANDOFF_ZYJ.md` 的「提测状态」一节，确认没有把待办写成已完成

---

## 四、提测之后

- 在平台确认提交记录真的生成了，再把状态从「已准备」改成「已提交」；
- 记录提交时间与平台返回的单号；
- **只有真的看到官方反馈或分数，才可以写进 `HANDOFF_ZYJ.md`**；
- 如果被判分有问题，用 `dify/validation/` 里的运行记录作为申诉依据。

---

## 五、本作品的提交物清单（对应官方题面 §4）

| 官方要求 | 文件 |
| --- | --- |
| §4.1 Dify DSL | `dify/workflow.yml`（单文件，注明适用 Dify 1.17.1、导入顺序=1 个文件） |
| §4.2 运行说明 | `dify/README.md`（创意/玩法、Dify 与 seekdb 分工、版本、依赖、完整步骤、入口、网络条件、已知限制、来源与许可） |
| §4.3 验证样例与运行证据 | `dify/examples/walkthrough.md`（7 个场景）+ `dify/validation/service_checks.md`（10 项自动检查）+ `dify/validation/workflow_checks.md`（Dify 端到端）+ `dify/validation/dsl_exported.yml`（导出的 DSL） |
| §4.4 自定义后端 | `dify/service/`（源码 + `requirements.txt` + `Dockerfile`）+ `dify/deploy/docker-compose.yml`（部署配置） |
| §4.4 数据初始化 | `dify/deploy/init_db.py`（建库建表建索引）+ `dify/README.md` §8（数据模型） |
| §4.4 依赖版本与来源 | `dify/README.md` §11（来源与许可表） |

官方题面还特别说明：**「Dify DSL 导出包含应用配置及知识库连接信息，但不包含知识库内容，相关数据需要单独交付或初始化」**——
本作品不使用知识库，所以没有额外的数据交付物；数据库侧的初始化由 `init_db.py` 负责，
并已在 §8 写明数据模型。
