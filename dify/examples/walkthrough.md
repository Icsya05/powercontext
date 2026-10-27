# 验证样例 · 午夜便利店

本文件是赛题要求的「**一组可以按步骤执行的完整样例**」：给出初始状态、输入、操作顺序、
预期表现，以及每一步该去哪里核对。

所有样例都可以在 Dify 应用的「运行 / 测试运行」面板里按顺序执行。

> 运行前提：`dify/README.md` §5.1–§5.7 已完成（seekdb + 记忆服务 + Dify + 模型 + 导入 DSL）。
>
> ⚠️ **最容易踩的坑**：Dify 的 HTTP 节点走自带的 Squid SSRF 代理，默认拒绝一切私有地址。
> 如果没有在 Dify 的 `docker/.env` 里设置
> `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal`，
> 「读取记忆」「写回记忆」两个节点会直接报
> `Access to '...' was blocked by SSRF protection`，后面的样例全部无法执行。
> 详见 `README.md` §5.6。
>
> 核对数据库用：
>
> ```bash
> # 方式 A：服务接口（不需要 mysql 客户端）
> curl http://127.0.0.1:8077/api/admin/players
> curl "http://127.0.0.1:8077/api/admin/turns?player_id=demo_001"
>
> # 方式 B：直接查 seekdb
> docker compose -f dify/deploy/docker-compose.yml exec seekdb \
>   mysql -h 127.0.0.1 -P 2881 -uroot -p"$SEEKDB_ROOT_PASSWORD" npc_memory \
>   -e "SELECT player_id, visit_count, bond_score, chapter, favourite FROM npc_player; \
>       SELECT id, player_id, turn_no, player_input FROM npc_turn ORDER BY id;"
> ```

---

## 样例 0：清空起点（保证每次验证可重复）

**初始条件**：数据库为空。

```bash
curl -X DELETE "http://127.0.0.1:8077/api/state?player_id=demo_001"
curl -X DELETE "http://127.0.0.1:8077/api/state?player_id=demo_002"
curl http://127.0.0.1:8077/api/admin/players      # 期望：{"ok":true,"players":[]}
```

---

## 样例 1：新玩家第一次到店（证明「没有记忆时不会假装认识」）

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_001` |
| 这一轮玩家说的话 | `推门进来，外面雨好大` |
| 操作 | `continue` |

**预期表现**

- 阿澈是**第一次**见这位客人，不会提起任何「上次」；
- 回答末尾出现 `（已记在账本里：第 1 次到店 ｜ 羁绊 … ｜ 章节「…」）`；
- 给出 3~4 个可选行动。

**数据库核对**

```bash
curl "http://127.0.0.1:8077/api/admin/turns?player_id=demo_001"
```

期望 `turns` 数组长度 = 1，`turn_no` = 1，且 `player_input` 等于「推门进来，外面雨好大」。

---

## 样例 2：同一玩家，**新会话**恢复记忆（核心验收项）

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_001`（**同一个**） |
| 这一轮玩家说的话 | `还是热可可吧，跟上次一样` |
| 操作 | `continue` |

> **关键**：在 Dify 里**新建一个会话**（或直接再点一次运行），不要继续上一轮对话。
> 这一步证明记忆来自 seekdb，而不是 Dify 的会话变量。

**预期表现**

- 阿澈的回应里出现样例 1 里存在过的具体细节（商品、天气、你们刚建立的梗，至少其一）；
- 回答末尾变成 `第 2 次到店 ｜ 羁绊 …`，羁绊值相对第一次有变化。

**数据库核对**

```bash
curl "http://127.0.0.1:8077/api/admin/turns?player_id=demo_001"
```

期望 `turns` 长度 = 2，`turn_no` 依次为 1、2；`npc_player.visit_count` = 2。

---

## 样例 3：中文全文检索确实参与召回

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_001` |
| 这一轮玩家说的话 | `热可可` |
| 操作 | `continue` |

**预期表现**：上下文里会出现「从历史对话里召回的往事」，且召回方式为 `fulltext`
（`fulltext-boolean` 也算通过）。

**数据库核对**

```bash
curl "http://127.0.0.1:8077/api/state?player_id=demo_001&query=热可可"
```

在返回的 JSON 里检查：

- `recall_mode` 为 `fulltext` 或 `fulltext-boolean`；
- `memories` 非空，且命中的回合里出现「热可可」。

> 对照实验：把查询词换成数据库里根本没有的内容（例如 `zzz不存在zzz`），
> `recall_mode` 会退化为 `like` 或 `recent`，用于说明检索确实在起作用而不是恒返回。

---

## 样例 4：玩家隔离（换一个卡号就是另一个人）

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_002`（**新卡号**） |
| 这一轮玩家说的话 | `推门进来，外面雨好大` |
| 操作 | `continue` |

**预期表现**

- 阿澈对 `demo_002` **完全不认识**，不会提 `demo_001` 的热可可、梗或到店次数；
- 回答末尾是 `第 1 次到店`。

**数据库核对**

```bash
curl http://127.0.0.1:8077/api/admin/players
# 期望：["demo_001","demo_002"]
curl "http://127.0.0.1:8077/api/state?player_id=demo_002"
# 期望：memories 为空，state 只有 demo_002 自己的字段
```

---

## 样例 5：重置（重新开始）

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_001` |
| 这一轮玩家说的话 | `（随便填，例如：算了）` |
| 操作 | `reset` |

**预期表现**

- 回答里出现「会员卡 demo_001 已注销，阿澈把记着你的那几页撕掉了」；
- 回答里**不会**出现「已记在账本里：第 N 次到店」。

**数据库核对**

```bash
curl "http://127.0.0.1:8077/api/admin/turns?player_id=demo_001"
# 期望：turns 为空数组
curl "http://127.0.0.1:8077/api/state?player_id=demo_001"
# 期望：found = false，memories 为空
curl http://127.0.0.1:8077/api/admin/players
# 期望：只剩 ["demo_002"] —— demo_002 未受影响
```

再跑一次样例 1，`demo_001` 会重新变成「第 1 次到店」，说明重置是彻底的。

---

## 样例 6：数据库不可用时明确报错（不假装记住）

**准备**：停掉 seekdb，保留记忆服务。

```bash
docker compose -f dify/deploy/docker-compose.yml stop seekdb
```

| 项 | 值 |
| --- | --- |
| 会员卡号 | `demo_002` |
| 这一轮玩家说的话 | `还是老样子` |
| 操作 | `continue` |

**预期表现**

- 工作流走**错误分支**（节点 `记忆可用？` → `记忆库不可用` → `结束（记忆库不可用）`）；
- 输出里明确写着「既没有读到任何记忆，也没有被写进账本」；
- **不会**出现「已记在账本里：第 N 次到店」。

**数据库核对（服务在、库不在）**

```bash
curl http://127.0.0.1:8077/api/health
# 期望：ok=false, db.ok=false
```

**恢复**

```bash
docker compose -f dify/deploy/docker-compose.yml start seekdb
```

---

## 样例 7：非法会员卡号

| 项 | 值 |
| --- | --- |
| 会员卡号 | `bad id!`（含空格和感叹号） |
| 这一轮玩家说的话 | `你好` |
| 操作 | `continue` |

**预期表现**：走错误分支，提示玩家标识非法（合法字符：字母、数字、`-`、`_`，长度 1–64）。

---

## 8. 一键跑完服务端到端检查

样例 1–7 的自动化版本（会真的写库、真的读回、真的把数据库打挂）：

```bash
python dify/validation/service_checks.py --base-url http://127.0.0.1:8077
```

它会依次执行 10 项检查并把证据写到
`dify/validation/service_checks.md` / `service_checks.json`：

| # | 检查项 | 验证的是赛题的哪一条 |
| --- | --- | --- |
| 1 | `health_db_reachable` | 服务与 seekdb 都活着 |
| 2 | `schema_present` | 表与中文全文索引真的建好了 |
| 3 | `new_player_has_no_memory` | 新玩家没有历史记忆 |
| 4 | `write_turn_persisted_in_seekdb` | 对话真的写进了 seekdb 并能读回 |
| 5 | `returning_player_recovers_state` | 同一玩家再次访问时记忆被恢复 |
| 6 | `memory_recall_uses_seekdb_fts` | 中文全文检索真的参与了召回 |
| 7 | `players_are_isolated` | 不同玩家数据完全隔离 |
| 8 | `reset_only_affects_target` | 重置只清除目标玩家 |
| 9 | `invalid_player_id_rejected` | 非法玩家标识被明确拒绝 |
| 10 | `db_unavailable_returns_clear_error` | 数据库不可用时返回明确错误而非伪造成功 |

---

## 9. 作品入口

- Dify 应用入口：`http://localhost/apps` → 「午夜便利店 · 阿澈会记得你」→ 「运行 / 测试运行」。
- 想给评审一个更顺手的入口，可以在 Dify 里为该应用开启 **API 访问**，
  用 `POST /v1/workflows/run` 触发同一轮对话（入参：`player_id`、`player_input`、`action`）。
