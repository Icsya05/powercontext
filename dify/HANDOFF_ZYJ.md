# HANDOFF：zyj 的 Dify 赛题作品

更新于 2026-10-27 22:20。本文件只记录**已经实际执行并验证过**的事，预测性内容一律标注为待办。

## 1. 位置

| 项目 | 值 |
| --- | --- |
| 仓库 | `Icsya05/powercontext`（私有，官方 `oceanbase/powercontext` 的导入仓库） |
| 分支 | `ecosystem/zyj-dify`（已推送到 origin） |
| 官方比赛基线 | `2026-competition-ecosystem` @ `d647275c308e09b7b623f322a26f5c4e85734fb0`（本分支的祖先） |
| 共同起点 | `competition/nearby-skill` @ `9ce99250bd92e4dd0aa2d124c0fb649619b4a408`（其父提交即官方基线） |
| 首个内容提交 | `ab7ac1dacb658ae658276570de8b1f32dc04757c` |
| 本文件所在提交 | 分支 HEAD（见 `git rev-parse ecosystem/zyj-dify`） |
| 文件归属 | 只动 `dify/`，未改 `src/powercontext/`、`gaode/`、`modelscope/`、CI、根级共享文件 |

## 2. 交付物

| 文件 | 作用 |
| --- | --- |
| `dify/workflow.yml` | **Dify 真实导出的 DSL**，13 个节点：读记忆 → 判断库可用 → LLM → 写回 → 回答。模型已绑定 `MiniMax-M3`（provider `langgenius/openai_api_compatible/openai_api_compatible`），并带 `dependencies`，导入时 Dify 会自动装对应插件 |
| `dify/service/app.py`、`db.py`、`config.py` | 记忆服务（FastAPI + PyMySQL），seekdb 数据访问层 |
| `dify/service/Dockerfile`、`requirements.txt` | 容器镜像与固定版本依赖 |
| `dify/service/Dockerfile.dockerignore` | 保证 `dify/.env`（含真实密码）不会被打进镜像层 |
| `dify/deploy/docker-compose.yml` | seekdb 1.4.0 + 记忆服务 |
| `dify/deploy/init_db.py` | 建库、建表、建中文全文索引 |
| `dify/deploy/capture_evidence.py` | 行级数据库证据导出（真写真读 + 全文召回 + 玩家隔离） |
| `dify/deploy/setup_dify_console.py` | 一次性创建 Dify 控制台管理员账号 |
| `dify/deploy/install_model_provider_plugin.py` | 从 Dify 官方 marketplace 安装 OpenAI 兼容模型供应商插件 |
| `dify/deploy/export_dsl_from_dify.py` | 从真实 Dify 导出 DSL 并存档 |
| `dify/deploy/check_dsl.py` | DSL 静态检查（离线可跑） |
| `dify/deploy/check_packaging.py` | 部署包静态检查（离线可跑） |
| `dify/validation/service_checks.py` + `.md` / `.json` | 记忆服务端到端检查（真实读写 / 隔离 / 重置 / 故障）**及其证据** |
| `dify/validation/workflow_checks.py` + `.md` / `.json` | Dify 全链路检查（导入 / 真跑 / 导出 / 重导入 / 再跑）**及其证据** |
| `dify/validation/dsl_roundtrip.py` + `.md` / `.json` | DSL 往返检查（不需要模型也能跑）**及其证据** |
| `dify/validation/dsl_exported.yml` | Dify 1.17.1 真实导出的 DSL 存档 |
| `dify/README.md` | 作品说明 + 从零运行步骤（含 MiniMax 配置清单） |
| `dify/REQUIREMENTS.md` | 官方要求逐条核对（含来源与状态） |
| `dify/examples/walkthrough.md` | 完整验证样例（7 个场景 + 自动化检查对照） |

## 3. 本轮实际做了什么

1. 读了官方 Dify 题面（S1）、算分规则（S2）、GitHub 使用说明（S3）、测试索引（S4），
   以及官方基线分支、官方 Dify 插件源码、seekdb 镜像文档、Dify 1.17.1 的 DSL 源码与测试夹具。
2. 确认官方基线分支 `2026-competition-ecosystem` 里 `dify/` 只有 `.gitkeep`，**没有模板**，
   因此格式完全以官方题面为准。
3. 选定 **seekdb 作应用数据存储**（而非用 seekdb 顶替 Dify 的 PostgreSQL）：
   官方 PowerContext Dify 插件自述不附带 DSL 模板且尚未进插件市场，评审侧无法稳定复现。
4. 实现记忆服务：`npc_player`（聚合状态）+ `npc_turn`（对话日志）+ `FULLTEXT INDEX ... WITH PARSER ik`（中文分词），
   召回走 `MATCH(content) AGAINST(...)`，失败时降级为 `LIKE` 并用 `recall_mode` 标明实际策略。
5. 写出 13 节点的 Dify DSL，并写 `check_dsl.py` 做静态校验：
   YAML 可解析、图的边都指向存在的节点、所有节点从 start 可达且都能到 end、
   每个 code 节点**实际执行** `main()` 并核对返回键与声明的 outputs 完全一致、
   所有 `{{#node.var#}}` 引用都指向真实存在的输出。
6. 查出并解决了 Dify 的 **SSRF 代理**问题（见 §5），这是让本地后端能被 Dify 调用的关键一步。
7. 在本机装起 Docker Desktop 4.97.0 + WSL 3.0.4.0，**真实**起 seekdb 1.4.0 与记忆服务，
   拿到真实的数据库读写证据（§4）。
8. 真实起 Dify 1.17.1（16 个容器），装 OpenAI 兼容模型供应商插件，
   **真实绑定 MiniMax-M3 并跑通完整对话**，把 seekdb 的行级证据、DSL 往返证据一起拿下。
9. 用 Dify 真实导出的 DSL **替换**了 `dify/workflow.yml`，保证交付的就是跑过的那一份。

## 4. 验证：哪些真实，哪些还没做

全部是**真实执行**的输出，没有任何模拟结果顶替。

| 项目 | 性质 | 结果 |
| --- | --- | --- |
| `python dify/deploy/check_dsl.py` | **真实执行**（离线） | `DSL OK: 13 nodes, 12 edges`；6 个 code 节点全部执行成功并返回声明的 outputs |
| `python dify/deploy/check_packaging.py` | **真实执行**（离线） | `packaging OK` |
| Docker 引擎 | **真实运行** | Docker Desktop 4.97.0.244584，Server 29.9.2，`hello-world` 通过，linux/overlayfs |
| seekdb 容器 | **真实运行** | `oceanbase/seekdb:1.4.0-100000172026082615` 容器 healthy，`db.ok=true`，用户 `root@sys`，库 `npc_memory` |
| 中文全文索引 | **真实运行** | `full-text parser: ik` —— `FULLTEXT INDEX ... WITH PARSER ik` 建表成功 |
| `python dify/deploy/init_db.py` | **真实执行** | `database: ready` / `tables: ready (full-text parser: ik)` |
| `python dify/validation/service_checks.py` | **真实执行** | **10 / 10 通过**（含：真写库、真读回、跨会话恢复、全文检索召回、玩家隔离、重置只清目标、非法卡号拒绝、库不可达报明确错） |
| `python dify/deploy/capture_evidence.py` | **真实执行** | 打印出 `npc_turn` / `npc_player` 的真实行；`recall_memories(player,'伞') -> mode=fulltext, 2 row(s)`；`player_999 found=False` |
| Dify 1.17.1 | **真实运行** | 16 个容器全部起来；`GET /console/api/setup` → `{"step":"not_started"}` → 建管理员 → 201 |
| 模型供应商插件 | **真实运行** | `langgenius/openai_api_compatible` **0.0.73** 安装成功（走官方 marketplace API） |
| Dify → 记忆服务通路 | **真实运行** | 从 `docker-api-1` 容器经 squid 代理访问 `http://host.docker.internal:8077/api/health` → HTTP 200，`db.ok=true` |
| 真实模型对话 | **真实运行** | MiniMax-M3 生成阿澈的回复，11 个节点全部执行，`status=succeeded`，1390 tokens |
| `python dify/validation/workflow_checks.py` | **真实执行** | **16 / 16 通过**（含：新玩家跑通 → 确实写进 seekdb → **新会话**恢复记忆（到店次数 +1）→ 玩家隔离 → 重置 → 导出 DSL → 干净应用重导入 → 再跑仍能写库） |
| `python dify/validation/dsl_roundtrip.py` | **真实执行** | **7 / 7 通过**：导出与源文件图结构一致；重导入后再导出**逐字节一致** |
| 官方提测 | ❌ **未执行** | 需要平台账号（见 §6） |
| 官方成绩 | ❌ 无 | 不宣称任何分数 |

> 表中「未执行」的项目没有任何模拟结果替代。

### 4.1 真实跑出来的证据样例

真实对话（MiniMax-M3，workflow run `succeeded`，11 steps）：

```
*玻璃门一开，裹进来的雨气把关东煮的热雾撞散了些。我从保温柜里摸出一瓶热牛奶，瓶身还烫。*
"第一次来？先把湿外套甩到肩上，别滴到货架上。热牛奶五块，扫码还是现金？"
```

这一轮在 seekdb `npc_turn` 里的真实行（`npc_player` 同步记 `visit_count=1`、`bond_score=1`、
`chapter=雨夜初遇`），由 `capture_evidence.py` 直接用 PyMySQL 读出。

## 5. 踩过并已解决的坑（对队友和评审都有用）

1. **Dify 的 SSRF 代理默认拒绝私有地址。**
   Dify 1.17.1 的 `docker/ssrf_proxy/squid.conf.template` 里有
   `http_access deny to_private_networks`（覆盖 10/8、172.16/12、192.168/16、127/8 等），
   所以本地记忆服务默认会被拦，HTTP 节点直接报
   `Access to '...' was blocked by SSRF protection`。
   解法：在 Dify 的 `docker/.env` 里设
   `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal`
   （`docker-entrypoint.sh` 会据此生成 `/etc/squid/dify_allow_private.conf` 放行 ACL）。
   **不设这一步，样例一步也跑不通。**
2. **seekdb 官方 README 里的数据目录路径已过时。**
   README 写 `/var/lib/oceanbase`，但镜像 1.4+ 实际是 `/var/lib/seekdb`
   （官方 docker-images 文档明确说明）。compose 文件已按 1.4 写。
3. **Windows 上 seekdb 必须用命名卷**，不能用宿主机目录挂载（官方文档明确要求）。
4. **pyseekdb 的嵌入式模式在 Windows 上不可用**：`pylibseekdb` 只有 Linux 构建，
   Windows 只能连服务端模式（`user@tenant` 形式，端口 2881）。服务已按该约定实现，
   并在租户名形式失败时自动回退到裸用户名。
5. **Dify DSL 的 HTTP 节点参数格式**是 `params`/`headers` 用 `Key: Value` 换行分隔、
   `body.data` 是字符串（`type: json` 时是 JSON 文本）。为避免中文进 query string，
   本作品改用 `POST` + JSON body，并由 code 节点用 `json.dumps` 生成，
   顺带解决用户输入里带引号会破坏 JSON 的问题。
6. **`StoreConfig` 在 import 时绑定 `os.getenv`，导致 `.env` 被整体忽略。**
   部署脚本是 `import dify.service.db` **之后**才 `load_env_file()`，
   所以模块加载时环境变量还不存在，密码读成空串，真实报错是
   `Access denied for user 'root'@'...' (using password: NO)`。
   改成 `dataclasses.field(default_factory=...)` 后每次实例化才解析环境。
   **这个问题只靠静态检查发现不了，必须真连一次库。**
7. **密码变量名不一致**：`StoreConfig` 读 `SEEKDB_PASSWORD`，而 `.env` 与 compose 用的是
   `SEEKDB_ROOT_PASSWORD`（compose 再把它映射成容器的 `SEEKDB_PASSWORD`）。
   现在两个名字都接受。
8. **compose 不能用命令行参数传 seekdb 密码。**
   镜像的 `/root/start.sh` 把**任何参数当成要执行的 SQL**，
   `command: ["-e", "ROOT_PASSWORD=..."]` 会让容器启动即退出。
   密码必须放在 `ROOT_PASSWORD` 环境变量里。
9. **`COPY dify` 会把 `dify/.env` 打进镜像层**（里面是真实的 seekdb 密码）。
   用 `dify/service/Dockerfile.dockerignore` 排除掉，并在镜像里验证过已无 `.env`。
10. **Dify 的导出接口返回的是 JSON 信封，不是裸 YAML。**
    `GET /console/api/apps/<id>/export` 返回 `{"data": "<yaml>"}`
    （`AppExportResponse`），直接当 YAML 用会得到「没有节点」的空图，
    重导入还会报 `Missing app data in YAML content`。
11. **Dify 的插件市场 API 形状**：`POST https://marketplace.dify.ai/api/v1/plugins/search/advanced`
    才能查到 `latest_package_identifier`（形如
    `langgenius/openai_api_compatible:0.0.73@<sha256>`），它同时也是
    `POST /console/api/workspaces/current/plugin/install/marketplace` 的入参。
12. **LLM 节点里的 provider 要写完整插件 ID**：
    `langgenius/openai_api_compatible/openai_api_compatible`，不是 `openai_api_compatible`
    （Dify 用 `ModelProviderID(provider)` 解析，`provider_name` 是最后一段）。
13. **Docker Desktop 安装包被截断会报「不是此操作系统平台的有效应用程序」。**
    这不是架构问题：PE 头声明的段长度超过文件实际长度，Windows 加载器直接拒绝。
    用 `curl -C - --retry` 重下并对照官方 `checksums.txt` 校验 SHA256 即可
    （本次：`https://desktop.docker.com/win/main/amd64/<build>/checksums.txt`）。
14. **git 不读 Windows 的系统代理，代理本身还可能把 TLS 搞坏。**
    这台机器开了 clash（系统代理 `127.0.0.1:7897`）。两种情况都遇到过：
    - 直连时 git push 失败（`Failed to connect to github.com:443`），
      加代理后正常：`git config --global http.proxy http://127.0.0.1:7897`（https.proxy 同理）；
    - 代理本身抽风时，git 报 `schannel: failed to receive handshake`，
      这时**去掉代理反而能通**：`git config --global --unset http.proxy`。

    所以遇到 push 失败时，两种配置都试一遍再下结论，不要直接判断"网络坏了"。
    提测前务必确认远端 commit 和本地一致：
    ```bash
    git ls-remote origin refs/heads/ecosystem/zyj-dify
    ```
15. **在 Windows 上原生编译 seekdb 的坑**（本机没有 Docker 时试过，现已不需要，供参考）：
    - 源码路径含中文时，CMake 配置阶段会以 `0xC0000409` 直接崩溃（无报错信息）。
      用 `subst S: <目录>` 映射成纯 ASCII 盘符后即可正常配置。
    - 配置阶段 CMake 会误用 PATH 里的 mingw `ld.exe`，报 `cannot find shell32.lib`；
      需要让 clang-cl 走 `lld-link` 并指向 Windows SDK 的 import lib。
    - 结论：这条路能做，但比 Docker 麻烦；正式交付以 Docker 路线为准。

## 6. 卡点与本人最少操作

| 卡点 | 最少操作 |
| --- | --- |
| ~~本机没有 Docker / WSL~~ | ✅ 已解决：本机装起 Docker Desktop 4.97.0.244584 + WSL 3.0.4.0，seekdb 与 Dify 1.17.1 都已真实跑起来 |
| ~~Dify 的 LLM 节点需要真实模型~~ | ✅ 已解决：zyj 在 Dify 界面配置了 MiniMax（`MiniMax-M3`，OpenAI 兼容），我已把模型绑进 DSL 并真实跑通 |
| 提交需要平台账号 | 登录 <https://open.oceanbase.com/train/detail/21>，进入 Dify 题目录提交 |
| 官方要求用带 PAT 的仓库地址 | 在 GitHub 为 `Icsya05/powercontext` 生成 PAT（scope `repo`），把 `https://<user>:<PAT>@github.com/Icsya05/powercontext` 填进参赛信息 |
| 评测方 clone 私有仓库 | 上述 PAT 填好之后，评测方即可 clone 本分支 `ecosystem/zyj-dify` |
| 生态分支合流 | 见 §9，需要队长在团队层面决定合流方式 |

凭据与 Token **不会**写入任何提交文件、README、日志或截图。
`dify/.env`（含 seekdb 密码与 Dify 控制台口令）已被 `.gitignore` 忽略，
并被 `dify/service/Dockerfile.dockerignore` 排除在镜像之外。

## 7. 与队友 xjl 的关系

- xjl 的分支是 `ecosystem/wyd-gaode-modelscope` @ `80a052d7`，交付 `gaode/` 与 `modelscope/`。
- 用 `git diff 9ce99250 80a052d7 --stat` 核对：15 个文件，**全部在 `gaode/` 与 `modelscope/`**；
  `dify/` 在两侧字节一致（只有 `.gitkeep`）。本任务与 xjl **没有重叠**。
- 本任务刻意**没有**改动 xjl 的任何文件，也没有改动 `src/powercontext/`、CI、根级共享文件。
- 本分支与 xjl 分支同源（共同起点 `9ce99250`），互不包含，可分别提 PR。

## 8. 下一步（按顺序）

1. ✅ ~~装好 Docker Desktop → 起 seekdb + 记忆服务 → 跑 `service_checks.py`~~（已完成，10/10）
2. ✅ ~~起 Dify 1.17.1 → 导入 DSL → 配模型 → 跑真实对话~~（已完成，16/16）
3. ✅ ~~导出 DSL → 干净应用重新导入 → 再跑一遍~~（已完成，7/7 逐字节一致）
4. ✅ ~~用导出的 DSL 替换 `dify/workflow.yml`~~（已完成，`dify/workflow.yml` 现在就是 Dify 真实导出的那一份）
5. ⬜ zyj 登录 OceanBase 社区 + 生成 PAT → 按提测指南提交，核对提交记录
6. ⬜ 队长决定生态分支合流方式（见 §9），合流后提测分支才同时含 `dify/`、`gaode/`、`modelscope/`
7. ⬜ （可选）把 §4.1 的真实对话整理成截图，作为评审证据

## 9. ⚠️ 需要团队层面处理的一件事：分支合流

本分支 `ecosystem/zyj-dify` 与队友的 `ecosystem/wyd-gaode-modelscope` **是并列的两条分支**，
互相不包含：

```text
d647275c  (官方基线 2026-competition-ecosystem)
   └── 9ce99250  competition/nearby-skill        ← 共同起点
         ├── ab7ac1da..<HEAD>    ecosystem/zyj-dify                （本任务：dify/）
         └── 80a052d7            ecosystem/wyd-gaode-modelscope     （xjl：gaode/ + modelscope/）
```

`git diff origin/ecosystem/wyd-gaode-modelscope ecosystem/zyj-dify -- gaode modelscope`
会看到 xjl 的 15 个文件在本分支上「不存在」——这是正常的，因为本任务没有也不会合并他们的分支。

但**提测平台要求提交的分支/commit hash 是「生态」的合流版本**（官方题面：提交分支须基于
`2026-competition-ecosystem`，相关资产放入对应目录）。因此在提测前需要有人把三条生态分支
（`zyj-dify`、`wyd-gaode-modelscope`，以及后续可能新增的）合并到一条提交分支上。

建议由**核心负责人 / 队长**执行合流（例如各人分别提 PR 到团队指定的合流分支），
避免任何一方直接改写他人的提交历史。合流后提测平台填的分支/commit 才同时包含
`dify/`、`gaode/`、`modelscope/` 三份资产。
