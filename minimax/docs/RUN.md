# 运行说明

> 《规有所依 —— 面向软件持续演进的 SDD 上下文管理系统》
> 本文是官方赛题「提交材料 → 运行说明」要求的交付物：从安装依赖到跑通验证样例的完整步骤。

---

## 1. 依赖与版本

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | **3.11 – 3.13**（实测 3.12.10） | 上下文模块与业务工程 |
| Docker / Docker Compose | v2.x（实测 Compose v5.6.1） | 跑 seekdb |
| seekdb | `oceanbase/seekdb:1.4.0-100000172026082615` | 工程资料存储与全文检索 |
| PowerContext | **1.4.1**（PyPI `powercontext[server,builtin,code,cli]`） | 任务状态存储 |
| pytest | 8.4.1 | 跑业务工程与模块自身的测试 |
| 模型服务 | 任意 OpenAI 兼容 Chat 接口（本作品实测 **MiniMax-M3**，`https://api.minimaxi.com/v1`） | **唯一可能产生费用的项** |

不需要 Embedding / Rerank 服务：召回用的是 seekdb 的中文全文索引（`WITH PARSER ik`）。

---

## 2. 配置步骤

### 2.1 准备凭据文件

在仓库根目录创建 `minimax/.env`（**该文件已被 `.gitignore` 忽略，不要提交**）。
模板见 `minimax/.env.example`。

```bash
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL=MiniMax-M3
MINIMAX_API_KEY=填入你的 MiniMax API Key

SEEKDB_HOST=127.0.0.1
SEEKDB_PORT=2881
SEEKDB_USER=root
SEEKDB_PASSWORD=填入 seekdb root 密码
SEEKDB_TENANT=sys
SEEKDB_DATABASE=sdd_context

POWERCONTEXT_URL=http://127.0.0.1:8000
POWERCONTEXT_SCOPE=sdd-demo
```

### 2.2 启动 seekdb

```bash
cd minimax
cat > .seekdb.env <<'EOF'
SEEKDB_ROOT_PASSWORD=<与 .env 里的 SEEKDB_PASSWORD 一致>
SEEKDB_DATABASE=sdd_context
EOF
docker compose -f deploy/docker-compose.yml --env-file .seekdb.env up -d
```

等 seekdb 起来（`docker compose ps` 显示 healthy）。
`deploy/docker-compose.yml` 只声明一个服务 `seekdb`，映射 `2881`（MySQL 协议）
与 `2886`（HTTP 服务），数据落在命名卷 `seekdb-data`。

### 2.3 安装并启动 PowerContext

PowerContext 是纯 Python 包，直接从 PyPI 装（**不需要克隆上游仓库**）：

```bash
python -m venv .venv-powercontext
. .venv-powercontext/bin/activate            # Windows: .venv-powercontext\Scripts\activate
pip install "powercontext[server,builtin,code,cli]==1.4.1"
```

准备服务配置（**放在仓库之外**，因为里面有真实 API Key）：

```bash
cp minimax/deploy/powercontext.env.example /abs/path/to/powercontext.env
# 编辑它，至少改这四项：
#   POWERCONTEXT_HOME=/abs/path/to/powercontext-data
#   POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:////abs/path/to/powercontext-data/powercontext.db
#   POWERCONTEXT_SERVER_INFERENCE_GENERATION_MODEL=openai:<你的模型名>
#   POWERCONTEXT_SERVER_INFERENCE_GENERATION_BASE_URL=https://api.minimaxi.com/v1
#   OPENAI_API_KEY=<你的 MiniMax API Key>
```

启动：

```bash
powercontext server run --env-file /abs/path/to/powercontext.env --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health/ready
# 期望 {"status":"ready", ... "inference.generation":"ready" ...}
```

> PowerContext 的 MCP 端点也在 `http://127.0.0.1:8000/mcp`，
> 与官方 `integrations/minimax` 插件用的是同一个地址；本作品走 HTTP API，
> 因为评审可以直接用 `curl` 核对每一条状态记录。

### 2.4 初始化数据

```bash
cd minimax
python -m sddctx import
```

这一条命令会：建 `sdd_context` 库、建三张表和中文全文索引、
解析 `specs/*.md` 与 `tasks/*.md`、用 AST 索引业务工程的代码符号与测试用例、
然后把它们写进 seekdb。输出形如：

```json
{"specs": 12, "code": 335, "tests": 87,
 "stored": {"specs": 12, "code": 335, "tests": 87}}
```

幂等：重复执行只会更新，不会重复插入。

---

## 3. 调用入口

上下文模块是一个命令行工具，入口 `python -m sddctx`（在 `minimax/` 目录下执行）。

| 命令 | 作用 |
| --- | --- |
| `python -m sddctx doctor` | 检查 seekdb / PowerContext / MiniMax 三者是否都可达 |
| `python -m sddctx import` | 把规格、代码符号、测试用例导入 seekdb |
| `python -m sddctx context --task T-2026-001` | 检索并组装开发上下文（可选 `--json` / `--out`） |
| `python -m sddctx testgen --task T-2026-001` | 让 MiniMax 按规格生成目标测试文件 |
| `python -m sddctx patch --task T-2026-001` | 让 MiniMax 产出补丁并用 `git apply` 应用 |
| `python -m sddctx test --task T-2026-001` | 运行任务声明的验收命令 |
| `python -m sddctx state --task T-2026-001` | 从 PowerContext 读回任务状态 |
| `python -m sddctx run --task T-2026-001` | 一键：import → context → testgen → patch → test → 存状态 |

辅助命令：

| 命令 | 作用 |
| --- | --- |
| `python -m validation.check_acceptance` | 自动核验官方六项必做项 |
| `python -m validation.reproduce_evidence` | 重建 before/after 证据链（回滚 → 失败 → 应用补丁 → 通过） |
| `python -m validation.write_artifacts` | 生成代码差异、状态快照、查询记录、模型用量等工件 |
| `python -m pytest sddctx/tests/test_sddctx.py -q` | 上下文模块自身的单元测试 |

---

## 4. 测试命令

```bash
# 业务工程的目标测试（本次任务新增）
cd minimax/sample_project/jmespath
python -m pytest tests/test_matches.py -q

# 业务工程的完整回归测试（含上游全部 991 个用例与合规测试）
python -m pytest tests/ -q

# 上下文模块自身的单元测试
cd ../../..
python -m pytest minimax/sddctx/tests/test_sddctx.py -q
```

---

## 5. 验证样例的完整流程

见 [`WALKTHROUGH.md`](WALKTHROUGH.md)。最短路径：

```bash
cd minimax
python -m sddctx doctor
python -m sddctx import
python -m sddctx context --task T-2026-001
python -m validation.reproduce_evidence     # 重建 before/after 证据
python -m validation.check_acceptance        # 核验六项必做项
```

---

## 6. 网络条件

| 场景 | 要求 |
| --- | --- |
| 上下文模块 → seekdb | `127.0.0.1:2881`（本机直连） |
| 上下文模块 → PowerContext | `127.0.0.1:8000`（本机直连） |
| 上下文模块 → MiniMax | 出网访问 `https://api.minimaxi.com/v1` |
| PowerContext → MiniMax | 同上（PowerContext 用它做推理提供者） |

模块**不经过**任何反向代理或 SSRF 过滤，访问的都是回环地址或公开 HTTPS 端点。

---

## 7. 已知限制

1. **模型能力上限**：MiniMax-M3 是推理模型，会把很大一部分输出预算花在 `<think>` 段上。
   模块默认 `max_tokens=32768`；若改用别的模型，这个值要相应调大，否则回答会被截断。
2. **补丁行数声明**：模型生成的 diff 偶尔会写错 hunk 头的行数。模块用
   `git apply --recount` 让 git 自行重算，并在失败时退回普通 `git apply`。
   如果两次都失败，模型会收到失败信息并在下一轮修正。
3. **seekdb 全文检索的召回**：中文分词依赖 seekdb 的 `ik` 分词器。
   如果目标镜像不带该分词器，模块会自动退回普通分词，并退回 `LIKE` 扫描，
   召回质量下降但流程仍可运行（检索模式会记录在证据里）。
4. **PowerContext 后台调度**：本作品不依赖后台调度器，
   `.env` 里把 `*_SCHEDULE_SECONDS` 调大、`DREAM_ENABLED` 设为 `false`，
   以免影响验证时的时序。
5. **业务工程是 vendored 副本**：`minimax/sample_project/jmespath/` 是上游
   jmespath.py v1.1.0 的拷贝，**不是** git submodule；它随本仓库一起提交，
   评审 clone 后即可运行，不需要额外拉取。
6. **只做了一次任务**：本作品只完成了一个开发任务（`T-2026-001`）。
   模块本身支持多任务（`--task` 参数 + 每个任务一份任务文档），
   但交付的验证证据只覆盖这一个任务。
