# HANDOFF：zyj 的 Dify 赛题作品

更新于 2026-10-27。本文件只记录**已经实际完成并验证过**的事，预测性内容一律标注为待办。

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
| `dify/workflow.yml` | Dify DSL，13 个节点：读记忆 → 判断库可用 → LLM → 写回 → 回答 |
| `dify/service/app.py`、`db.py`、`config.py` | 记忆服务（FastAPI + PyMySQL），seekdb 数据访问层 |
| `dify/service/Dockerfile`、`requirements.txt` | 容器镜像与固定版本依赖 |
| `dify/deploy/docker-compose.yml` | seekdb 1.4.0 + 记忆服务 |
| `dify/deploy/init_db.py` | 建库、建表、建中文全文索引 |
| `dify/deploy/check_dsl.py` | DSL 静态检查（离线可跑） |
| `dify/validation/service_checks.py` | 记忆服务端到端检查（真实读写 / 隔离 / 重置 / 故障） |
| `dify/README.md` | 作品说明 + 从零运行步骤 |
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

## 4. 验证：哪些真实，哪些还没做

| 项目 | 性质 | 结果 |
| --- | --- | --- |
| `python dify/deploy/check_dsl.py` | **真实执行**（离线） | `DSL OK: 13 nodes, 12 edges`；6 个 code 节点全部执行成功并返回声明的 outputs |
| 记忆服务启动 + `/api/health` | **真实运行** | 服务正常监听 8077；`db.ok=false`（此时还没有 seekdb） |
| `/api/state?player_id=bad!id` | **真实运行** | 返回 `code=INVALID_PLAYER_ID` + 中文说明 |
| `/api/state`、`/api/turn`（库不可达） | **真实运行** | 返回 `code=DB_UNAVAILABLE` + 可读中文错误，**没有**伪造记忆 |
| `POST /api/state`、`POST /api/turn?action=reset`、`GET /api/admin/schema` | **真实运行** | 路由正确，错误语义正确 |
| 响应编码 | **真实执行** | 用 Python 解码后中文完全正确（`decoded ok: True`） |
| seekdb 真实读写（建表、写行、全文检索召回） | ❌ **未执行** | 需要先有 seekdb 实例（见 §6 U1） |
| `dify/validation/service_checks.py` 全 10 项 | ❌ **未执行** | 同上，需要 seekdb |
| Dify 导入 DSL / 运行工作流 / 导出 / 重新导入 | ❌ **未执行** | 需要先有 Dify 实例（见 §6 U1、U5） |
| 官方提测 | ❌ **未执行** | 需要平台账号（见 §6 U2–U4） |
| 官方成绩 | ❌ 无 | 不宣称任何分数 |

> 表中「未执行」的项目没有任何模拟结果替代。

## 5. 踩过并已解决的坑（对队友和评审都有用）

1. **Dify 的 SSRF 代理默认拒绝私有地址。**
   Dify 1.17.1 的 `docker/ssrf_proxy/squid.conf.template` 里有
   `http_access deny to_private_networks`（覆盖 10/8、172.16/12、192.168/16、127/8 等），
   所以本地记忆服务默认会被拦，HTTP 节点直接报
   `Access to '...' was blocked by SSRF protection`。
   解法：在 Dify 的 `docker/.env` 里设
   `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal`
   （`docker-entrypoint.sh` 会据此生成放行 ACL）。
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
6. **在 Windows 上原生编译 seekdb 的两个坑**（本机没有 Docker 时试过，供参考）：
   - 源码路径含中文时，CMake 配置阶段会以 `0xC0000409` 直接崩溃（无报错信息）。
     用 `subst S: <目录>` 映射成纯 ASCII 盘符后即可正常配置。
   - 依赖初始化会从 `https://mirrors.oceanbase.com/oceanbase/development-kit/windows/11/x86_64`
     下载 cmake / ninja / LLVM 18 / flex-bison / vcpkg 等（约 367 秒），工具链随仓库走。
   - 配置阶段 CMake 会误用 PATH 里的 mingw `ld.exe`，报 `cannot find shell32.lib`；
     需要让 clang-cl 走 `lld-link` 并指向 Windows SDK 的 import lib。
   - 结论：这条路能做，但比 Docker 麻烦；正式交付仍以 Docker 路线为准。

## 6. 卡点与本人最少操作

| 卡点 | 最少操作 |
| --- | --- |
| 本机没有 Docker，也没有 WSL，当前**非管理员**权限，无法自行安装容器运行时 | 安装 **Docker Desktop**（Windows 11 家庭版需 WSL2，安装时会有一次 UAC 提权，可能需要重启一次）。装好后我就能在本机起 seekdb 与 Dify 1.17.1，做真实读写、真实导入导出、真实运行截图 |
| Dify 的 LLM 节点需要真实模型 | 在 Dify「模型提供商」里配置任意 OpenAI 兼容 Chat 模型（自带 API Key），或给我一个可用端点 + Key。**唯一可能产生费用的项**，我不会自行开通 |
| 提交需要平台账号 | 登录 <https://open.oceanbase.com/train/detail/21>，进入 Dify 题目录提交 |
| 官方要求用带 PAT 的仓库地址 | 在 GitHub 为 `Icsya05/powercontext` 生成 PAT（scope `repo`），把 `https://<user>:<PAT>@github.com/Icsya05/powercontext` 填进参赛信息 |
| 评测方 clone 私有仓库 | 上述 PAT 填好之后，评测方即可 clone 本分支 `ecosystem/zyj-dify` |

凭据与 Token **不会**写入任何提交文件、README、日志或截图。

## 7. 与队友 xjl 的关系

- xjl 的分支是 `ecosystem/wyd-gaode-modelscope` @ `80a052d7`，交付 `gaode/` 与 `modelscope/`。
- 用 `git diff 9ce99250 80a052d7 --stat` 核对：15 个文件，**全部在 `gaode/` 与 `modelscope/`**；
  `dify/` 在两侧字节一致（只有 `.gitkeep`）。本任务与 xjl **没有重叠**。
- 本任务刻意**没有**改动 xjl 的任何文件，也没有改动 `src/powercontext/`、CI、根级共享文件。
- 本分支与 xjl 分支同源（共同起点 `9ce99250`），互不包含，可分别提 PR。

## 8. 下一步（按顺序）

1. 装好 Docker Desktop → 我起 seekdb 1.4.0 + 记忆服务，跑 `dify/validation/service_checks.py`
   拿到真实的数据库读写证据（10 项全绿）。
2. 起 Dify 1.17.1 → 导入 `dify/workflow.yml` → 配模型 → 跑 7 个样例 → 截图。
3. 导出 DSL → 在干净的新应用里重新导入 → 再跑一遍 → 把两份 DSL 的差异记录下来。
4. 用导出的 DSL **替换** `dify/workflow.yml`（保证交付的是真跑过的那份），再提交。
5. 用户登录平台 + 提供 PAT → 按提测指南提交，核对提交记录。
