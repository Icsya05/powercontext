# 午夜便利店 · 阿澈会记得你

> 一个深夜便利店里的夜班店员，和一本**真的存在数据库里**的账本。
> 你换一台电脑、换一个会话再来，他还记得你上次点了什么、上次说过什么、你们之间那个梗。

* **Dify** 负责全部流程编排：读记忆、调用模型、写回记忆、分支判断、组织回答。
* **seekdb** 负责长期记忆：会员状态、历史对话，以及中文全文检索（`MATCH ... AGAINST`）。

这是 2026 OceanBase 数据库大赛 **Dify 赛题**的参赛作品（题目满分 20 分，见 `REQUIREMENTS.md`）。

---

## 1. 作品创意与玩法

### 1.1 设定

便利店的账本上，除了流水，还夹着客人留下的便条。
夜班店员**阿澈**（24 岁，冷幽默，其实很在意每一个常客）会把这些便条收在收银机下面——
那本账本就是 seekdb。

### 1.2 玩法（三种输入，一次跑完一轮）

| 输入 | 说明 |
| --- | --- |
| `会员卡号` | 玩家的唯一标识（1–64 位字母/数字/`-`/`_`）。**换卡号 = 换一个玩家**，互相看不到对方的记忆。 |
| `这一轮玩家说的话` | 玩家这一轮的台词。第一次来可以只写「推门进来」。 |
| `操作` | `continue`（继续）或 `reset`（注销会员卡，抹掉这个玩家的全部记忆）。 |

每一轮，阿澈会：

1. 从 seekdb 读出这位客人的**状态**（到店次数、羁绊值、当前章节、常点商品、专属梗）；
2. 用 seekdb 的**中文全文检索**从历史对话里召回与本轮相关���**往事**；
3. 把这些交给模型，生成回应 + 3~4 个可选行动；
4. 把本轮**写回** seekdb（对话进 `npc_turn`，聚合状态进 `npc_player`）；
5. 回答里带上「已记在账本里：第 N 次到店 ｜ 羁绊 X ｜ 章节「…」」。

### 1.3 三件能立刻看懂的事

- **跨会话记忆**：换一个新会话、换一台机器，只要卡号一样，阿澈会主动提起上次的事。
  这不是 Dify 的会话变量——记忆每次都真的从 seekdb 读出来。
- **玩家隔离**：另一个卡号是另一个人，看不到前一个人的任何内容。
- **数据库不可用就说实话**：seekdb 挂掉时，工作流走错误分支，明确告诉你「这一轮既没有读到记忆，
  也没有被写进账本」，**不会假装记住了你**。

---

## 2. Dify 与 seekdb 的分工

```
玩家输入
   │
   ▼
┌──────────────────────────── Dify Workflow (dify/workflow.yml) ───────────────────────────┐
│                                                                                          │
│  开始 → 整理请求 → 读取记忆 ──→ 校验读取结果 ──→ 【记忆可用？】                          │
│   (code)      (code)       (http-request)   (code)        (if-else)                    │
│                                    │                          │                          │
│                    ┌───────────────┴──────────┐               │ true                     │
│                    │ false                     │               ▼                          │
│                    ▼                          │        记忆库不可用 → 明确报错 → 结束      │
│            组装记忆上下文 (code)               │                                          │
│                    ▼                          │                                          │
│              阿澈回应 (llm)                    │                                          │
│                    ▼                          │                                          │
│            解析模型输出 (code)                  │                                          │
│                    ▼                          │                                          │
│            写回记忆 (http-request) ──→ 生成答复 (code) → 结束                               │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                      │  MySQL 协议 (2881)
                                      ▼
                         ┌─────────────────────────────┐
                         │  seekdb 1.4.0              │
                         │  npc_player  状态表         │
                         │  npc_turn    对话日志        │
                         │  + 中文全文索引 (IK 分词)   │
                         └─────────────────────────────┘
```

- **Dify（必选）**：承担输入处理、HTTP 调用、模型调用、条件判断（数据库可用性分支）与结果输出。
- **seekdb（至少一种，已选用）**：承担**应用数据存储 + 检索**。存玩家聚合状态与全部历史对话；
  每一轮都真实 INSERT / UPDATE / SELECT；召回历史时走 seekdb 的中文全文索引。

> 为什么不用 PowerContext：官方 PowerContext Dify 插件自述「**不附带任何 Workflow/Chatflow DSL 模板**」，
> 且尚未进入 `langgenius/dify-plugins`（追踪 issue #1837），评审侧无法稳定复现。
> 赛题允许 seekdb / PowerContext 二选一，因此选择更易复现的 seekdb 路线。详见 `REQUIREMENTS.md` §5.1。

---

## 3. 目录结构

```text
dify/
├── README.md                     本文件：作品说明与从零运行步骤
├── REQUIREMENTS.md               官方要求逐条核对（含来源与状态）
├── HANDOFF_ZYJ.md                交接：分支、SHA、验证与提测状态
├── workflow.yml                  Dify DSL（唯一需要导入的应用文件）
├── .env.example                  配置占位值（无任何真实密钥）
├── service/                      记忆服务（Dify 与 seekdb 之间的桥）
│   ├── app.py                    FastAPI 路由
│   ├── db.py                     seekdb 数据访问层
│   ├── config.py                 .env 读取
│   ├── requirements.txt          固定版本依赖
│   └── Dockerfile                容器镜像
├── deploy/
│   ├── docker-compose.yml        seekdb + 记忆服务
│   ├── init_db.py                建库建表建索引
│   └── check_dsl.py              DSL 静态检查（离线可用）
├── examples/
│   └── walkthrough.md            完整验证样例（初始状态 / 输入 / 步骤 / 预期）
└── validation/
    ├── service_checks.py         记忆服务端到端检查（真实读写 / 隔离 / 重置 / 故障）
    ├── service_checks.md         上一次运行的证据
    └── service_checks.json       上一次运行的原始数据
```

---

## 4. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Docker / Docker Compose | v2.x | 跑 seekdb、记忆服务、Dify |
| Dify | **1.17.1** | 官方插件 README 的 CI 固定版本；DSL 版本 `0.7.0` |
| seekdb | `oceanbase/seekdb:1.4.0-100000172026082615` | 对应 seekdb v1.4.0 |
| Python | 3.12 | 与 Dify 插件运行时一致；仅本机跑脚本时需要 |
| 模型服务 | 任意 OpenAI 兼容 Chat 模型 | 在 Dify「模型提供商」里配置；**唯一可能产生费用的项** |

不需要 Embedding / Rerank 服务：语义召回用 seekdb 的中文全文索引实现。

---

## 5. 从零启动

> 以下命令在**仓库根目录**执行。

### 5.1 复制配置

```bash
cp dify/.env.example dify/.env
# 编辑 dify/.env，至少设置 SEEKDB_ROOT_PASSWORD（任意非空字符串）
```

### 5.2 启动 seekdb 与记忆服务

```bash
docker compose -f dify/deploy/docker-compose.yml --env-file dify/.env up -d
```

等两个容器都 healthy：

```bash
docker compose -f dify/deploy/docker-compose.yml ps
curl http://127.0.0.1:8077/api/health
# 期望：{"ok":true,"service":"up","db":{"ok":true,...}}
```

> Windows 上 seekdb 数据目录使用 Docker **命名卷**（镜像 1.4+ 的路径是 `/var/lib/seekdb`），
> compose 文件已经这样配置，不要改成宿主机目录挂载。

### 5.3 初始化表与中文全文索引

```bash
python dify/deploy/init_db.py --env dify/.env
# 期望：database: ready / tables: ready (full-text parser: ik)
```

也可以直接调用服务接口：`curl -X POST http://127.0.0.1:8077/api/admin/init`。

### 5.4 启动 Dify 1.17.1

```bash
git clone --branch 1.17.1 --depth 1 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
docker compose up -d
```

Dify 默认入口：<http://localhost/install>（首次访问设置管理员账号），
控制台 <http://localhost/apps>。

### 5.5 配置模型

Dify 控制台 → 右上角头像 → **设置 → 模型供应商** → 安装并配置任意 OpenAI 兼容提供商
（例如 `openai_api_compatible`，填入自己的 API Key 与 Base URL）。

> 模型 Key 只填在 Dify 界面里。**不要**写进本仓库的任何文件。

### 5.6 放行记忆服务的网络地址（**必做**，否则 HTTP 节点会被 SSRF 拦截）

Dify 的 HTTP Request 节点会经过它自带的 Squid SSRF 代理。该代理默认
`http_access deny to_private_networks`，**会把 10/8、172.16/12、192.168/16、
127/8 等私有地址全部拒绝**。记忆服务跑在本机或内网，因此默认会被拦掉，
表现为 HTTP 节点报 `Access to '...' was blocked by SSRF protection`。

在 **Dify 的 `docker/.env`** 里加一行（然后 `docker compose up -d` 重建 `ssrf_proxy`）：

```bash
# 放行记忆服务用到的域名（推荐：只放行这一个名字）
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal
```

如果你的记忆服务用的是 compose 服务名，就写那个名字，例如：

```bash
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal,memory-service
```

也可以按网段放行：

```bash
SSRF_PROXY_ALLOW_PRIVATE_IPS=172.16.0.0/12,192.168.0.0/16
```

> 本地演示也可以直接把 SSRF 代理关掉（在 `docker/.env` 里把
> `SSRF_PROXY_HTTP_URL` / `SSRF_PROXY_HTTPS_URL` 置空）。
> 两种方式任选其一；**不做这一步，HTTP 节点一定失败**。

### 5.7 导入 DSL

Dify 控制台 → **工作室 → 创建应用 → 导入 DSL 文件** → 选择 `dify/workflow.yml`。

导入后做两件事：

1. **绑定模型**：打开「阿澈回应」节点，把模型换成你在 §5.5 里配置好的模型
   （DSL 里预填的是 `openai_api_compatible / gpt-4o-mini`，换成你自己的即可）。
2. **确认记忆服务地址**：打开「读取记忆」和「写回记忆」两个 HTTP 节点，确认 URL 是
   `http://host.docker.internal:8077/...`。

   - Docker Desktop（Windows / macOS）：默认就是 `host.docker.internal`，**不用改**。
   - Linux 上的 Docker：给 Dify 的 `api` 服务加一行再重启：
     ```yaml
     extra_hosts:
       - "host.docker.internal:host-gateway"
     ```
     或者把两个节点的 URL 直接改成你机器的实际地址。
   - 记忆服务和 Dify 在同一个 compose 网络里：改成 `http://memory-service:8077/...`，
     并把 `memory-service` 也加进 §5.6 的 `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS`。

### 5.8 体验

在应用的「运行」/「测试运行」里填：

| 字段 | 值 |
| --- | --- |
| 会员卡号 | `demo_001` |
| 这一轮玩家说的话 | `推门进来，外面雨好大` |
| 操作 | `continue` |

点运行，看输出。再点一次「运行」——**同一张卡号**、同样输入，回复里应该出现你上次说过的话。

---

## 6. 验证样例

完整的验证样例（初始状态、输入、操作顺序、预期表现）在 **`examples/walkthrough.md`**，
覆盖赛题验收要求的五条：

1. 新玩家首次到店；
2. 同一玩家**在新会话**中恢复记忆；
3. 两个不同玩家互相隔离；
4. 重置后回到「第一次来」的状态；
5. 数据库不可用时给出明确错误。

服务端的自动化检查（会真的写库、真的读回、真的把数据库打挂）：

```bash
python dify/validation/service_checks.py --base-url http://127.0.0.1:8077
```

输出写入 `dify/validation/service_checks.md` 与 `.json`。

Dify 侧的端到端检查（导入 DSL → 真跑 → 导出 → 重新导入 → 再跑）：

```bash
python dify/validation/workflow_checks.py \
    --dify-url http://localhost \
    --email YOUR_DIFY_EMAIL --password YOUR_DIFY_PASSWORD \
    --memory-url http://127.0.0.1:8077
```

它使用 Dify 控制台 API（与 Dify 官方 e2e 同一套流程）完成导入、发布、运行、导出、重新导入，
并用记忆服务接口核对数据库里的真实行。报告写入 `dify/validation/workflow_checks.md`，
导出的 DSL 写入 `dify/validation/dsl_exported.yml`。

---

## 7. 记忆服务接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务与 seekdb 连通性 |
| `GET`/`POST` | `/api/state` | 读玩家状态 + 召回往事（`player_id`、`query`） |
| `POST` | `/api/turn` | 写入一轮对话；`action=reset` 时执行重置 |
| `DELETE` | `/api/state` | 重置某个玩家 |
| `POST` | `/api/admin/init` | 建库建表建索引 |
| `GET` | `/api/admin/schema` | 导出真实的表与索引信息（证据用） |
| `GET` | `/api/admin/players` | 列出所有玩家 |
| `GET` | `/api/admin/turns` | 导出某个玩家的原始对话行（证据用） |

约定：**所有响应都带 `ok` 字段**。`ok=false` 时 `code` 说明原因、`message` 是给人看的说明。

---

## 8. 数据模型

```sql
CREATE TABLE npc_player (              -- 玩家聚合状态
  player_id     VARCHAR(64)  PRIMARY KEY,   -- 会员卡号
  display_name  VARCHAR(64),
  visit_count   INT,                        -- 到店次数
  bond_score    INT,                        -- 羁绊值
  chapter       VARCHAR(64),                -- 当前章节
  favourite     VARCHAR(128),               -- 常点商品
  running_joke  VARCHAR(256),               -- 专属梗
  last_input    VARCHAR(512),
  last_reply    VARCHAR(1000),
  first_seen_at DATETIME, last_seen_at DATETIME, updated_at DATETIME
);

CREATE TABLE npc_turn (                -- 对话日志
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  player_id  VARCHAR(64),
  turn_no    INT,
  chapter    VARCHAR(64),
  player_input VARCHAR(500),
  npc_reply  VARCHAR(1000),
  choices    VARCHAR(512),
  content    TEXT,                     -- player_input + npc_reply
  created_at DATETIME,
  KEY idx_npc_turn_player (player_id, turn_no),
  FULLTEXT INDEX idx_npc_turn_fts (content) WITH PARSER ik   -- 中文分词
);
```

召回语句（**真实使用 seekdb 的全文索引**）：

```sql
SELECT id, turn_no, chapter, player_input, npc_reply
FROM npc_turn
WHERE player_id = %s
  AND MATCH(content) AGAINST (%s)          -- 或 ... IN BOOLEAN MODE
ORDER BY turn_no DESC LIMIT 4;
```

若该 seekdb 构建没有 `ik` 分词器，初始化脚本会自动退回默认分词器；
若全文检索不可用，召回自动降级为 `LIKE` 扫描，并在响应里用 `recall_mode` 标明实际使用的策略
（`fulltext` / `fulltext-boolean` / `like` / `recent`），不隐瞒。

---

## 9. 错误处理

| 场景 | 行为 |
| --- | --- |
| seekdb 不可达（服务在、库挂了） | 服务返回 `ok=false, code=DB_UNAVAILABLE` + 中文说明；Dify 走**错误分支**，明确告诉玩家这一轮没有被记住 |
| 记忆服务整体不可达 | Dify 的 HTTP 节点直接报错（节点级失败），不会返回伪造结果 |
| 非法会员卡号 | 服务返回 `code=INVALID_PLAYER_ID`，工作流走错误分支 |
| 模型返回的不是合法 JSON | 代码节点会剥掉 markdown 围栏、截取最外层 JSON；仍失败则保留原文作为回复，并在 `parse_note` 标记 `fallback` |
| 模型返回超长 / 越界字段 | 服务端截断（回复 1000 字、选项 4 条、羁绊增量 ±10） |
| 写入失败 | 最终答复里明确写「没有写进账本」，**不会假装记住了你** |

---

## 10. 已知限制

- **记忆服务地址需要一次确认**：`workflow.yml` 里写死 `http://host.docker.internal:8077`。
  Linux Docker 环境需要按 §5.6 加一行 `extra_hosts`，或手动改两个 URL。
- **记忆服务整体不可达时**，Dify 会以 HTTP 节点失败的形式呈现错误（而不是应用自定义文案），
  因为自定义错误分支依赖服务本身能应答。
- **向量检索未启用**：seekdb 支持向量索引（`VECTOR INDEX ... WITH (DISTANCE=l2, TYPE=hnsw)`），
  但向量检索需要 Embedding 服务，会引入额外依赖与费用。本作品用中文全文检索做召回。
- **一次运行 = 一轮对话**：工作流模式（非 Chatflow），一轮一次调用，便于逐轮核对数据库记录。
- 绑定过的模型凭据不会随 DSL 导出，导入后需在界面重新选择模型（见 §5.6）。

---

## 11. 来源与许可

| 组件 | 来源 | 许可 |
| --- | --- | --- |
| Dify | https://github.com/langgenius/dify （1.17.1） | Apache-2.0（部分子目录另有声明，以仓库为准） |
| seekdb | https://github.com/oceanbase/seekdb （v1.4.0） | Apache-2.0 |
| `pyseekdb` | https://pypi.org/project/pyseekdb/ （1.4.0.post1，仅用于交叉核对连接约定） | Apache-2.0 |
| FastAPI / Uvicorn / PyMySQL / pydantic | PyPI | MIT / BSD / MIT |
| `dify/service/`、`dify/deploy/`、`dify/validation/`、`dify/workflow.yml` | 本次比赛原创 | 随仓库 LICENSE |

本目录的第三方依赖版本固定在 `dify/service/requirements.txt` 与
`dify/deploy/docker-compose.yml`；未复制任何未授权的代码或素材。
