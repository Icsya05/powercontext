# seekdb 记忆服务验证记录

- 运行时间：2026-10-27T18:01:13
- 服务地址：`http://127.0.0.1:8077`
- 结果：**2 通过 / 8 失败**

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | health_db_reachable | FAIL | 服务与 seekdb 均可达 —— CheckFailure: seekdb is not reachable: {'ok': False, 'service': 'up', 'db': {'ok': False, 'host': '127.0.0.1', 'port': 2881, 'user': 'root@sys', 'database': 'npc_memory', 'fts_parser': 'ik'}, 'message': 'seekdb 不可用：记忆读写全部失败'} |
| 2 | schema_present | FAIL | seekdb 中存在表与中文全文索引 —— CheckFailure: schema introspection failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 3 | new_player_has_no_memory | FAIL | 新玩家首次访问没有历史记忆 —— CheckFailure: state read failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 4 | write_turn_persisted_in_seekdb | FAIL | 对话真实写入 seekdb 并可读回 —— CheckFailure: turn save failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本轮对话没有被保存：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 5 | returning_player_recovers_state | FAIL | 同一玩家再次访问时记忆被恢复 —— CheckFailure: second turn failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本轮对话没有被保存：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 6 | memory_recall_uses_seekdb_fts | FAIL | 中文全文检索从历史对话中召回往事 —— CheckFailure: recall failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 7 | players_are_isolated | FAIL | 不同玩家之间数据完全隔离 —— CheckFailure: isolation read failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 8 | reset_only_affects_target | FAIL | 重置只清除目标玩家，其他玩家不受影响 —— CheckFailure: reset failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，重置没有完成：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)") | root: (2003, "Can\'t connect to MySQL server on \'127.0.0.1\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")'} |
| 9 | invalid_player_id_rejected | PASS | 非法玩家标识被明确拒绝 |
| 10 | db_unavailable_returns_clear_error | PASS | 数据库不可用时返回明确错误而非伪造成功 |

## 每项检查的原始返回

### 1. health_db_reachable

```json
{
  "name": "health_db_reachable",
  "description": "服务与 seekdb 均可达",
  "status": "FAIL",
  "error": "CheckFailure: seekdb is not reachable: {'ok': False, 'service': 'up', 'db': {'ok': False, 'host': '127.0.0.1', 'port': 2881, 'user': 'root@sys', 'database': 'npc_memory', 'fts_parser': 'ik'}, 'message': 'seekdb 不可用：记忆读写全部失败'}",
  "duration_ms": 4098
}
```

### 2. schema_present

```json
{
  "name": "schema_present",
  "description": "seekdb 中存在表与中文全文索引",
  "status": "FAIL",
  "error": "CheckFailure: schema introspection failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4090
}
```

### 3. new_player_has_no_memory

```json
{
  "name": "new_player_has_no_memory",
  "description": "新玩家首次访问没有历史记忆",
  "status": "FAIL",
  "error": "CheckFailure: state read failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4108
}
```

### 4. write_turn_persisted_in_seekdb

```json
{
  "name": "write_turn_persisted_in_seekdb",
  "description": "对话真实写入 seekdb 并可读回",
  "status": "FAIL",
  "error": "CheckFailure: turn save failed: HTTP 200 {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本轮对话没有被保存：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4099
}
```

### 5. returning_player_recovers_state

```json
{
  "name": "returning_player_recovers_state",
  "description": "同一玩家再次访问时记忆被恢复",
  "status": "FAIL",
  "error": "CheckFailure: second turn failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本轮对话没有被保存：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4143
}
```

### 6. memory_recall_uses_seekdb_fts

```json
{
  "name": "memory_recall_uses_seekdb_fts",
  "description": "中文全文检索从历史对话中召回往事",
  "status": "FAIL",
  "error": "CheckFailure: recall failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4112
}
```

### 7. players_are_isolated

```json
{
  "name": "players_are_isolated",
  "description": "不同玩家之间数据完全隔离",
  "status": "FAIL",
  "error": "CheckFailure: isolation read failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4120
}
```

### 8. reset_only_affects_target

```json
{
  "name": "reset_only_affects_target",
  "description": "重置只清除目标玩家，其他玩家不受影响",
  "status": "FAIL",
  "error": "CheckFailure: reset failed: {'ok': False, 'code': 'DB_UNAVAILABLE', 'message': '记忆库暂时不可用，重置没有完成：cannot connect to seekdb at 127.0.0.1:2881 (root@sys): root@sys: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can\\'t connect to MySQL server on \\'127.0.0.1\\' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")'}",
  "duration_ms": 4103
}
```

### 9. invalid_player_id_rejected

```json
{
  "ok": false,
  "code": "INVALID_PLAYER_ID",
  "message": "玩家标识无效：player_id must be 1-64 characters of letters, digits, '-' or '_'"
}
```

### 10. db_unavailable_returns_clear_error

```json
{
  "error_body": {
    "ok": false,
    "code": "DB_UNAVAILABLE",
    "message": "记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:58839 (root@sys): root@sys: (2003, \"Can't connect to MySQL server on '127.0.0.1' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can't connect to MySQL server on '127.0.0.1' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")"
  },
  "health": {
    "ok": false,
    "service": "up",
    "db": {
      "ok": false,
      "host": "127.0.0.1",
      "port": 58839,
      "user": "root@sys",
      "database": "npc_memory",
      "fts_parser": "ik"
    },
    "message": "seekdb 不可用：记忆读写全部失败"
  },
  "dead_port": 58839
}
```
