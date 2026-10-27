# seekdb 记忆服务验证记录

- 运行时间：2026-10-27T19:31:08
- 服务地址：`http://127.0.0.1:8077`
- 结果：**10 通过 / 0 失败**

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | health_db_reachable | PASS | 服务与 seekdb 均可达 |
| 2 | schema_present | PASS | seekdb 中存在表与中文全文索引 |
| 3 | new_player_has_no_memory | PASS | 新玩家首次访问没有历史记忆 |
| 4 | write_turn_persisted_in_seekdb | PASS | 对话真实写入 seekdb 并可读回 |
| 5 | returning_player_recovers_state | PASS | 同一玩家再次访问时记忆被恢复 |
| 6 | memory_recall_uses_seekdb_fts | PASS | 中文全文检索从历史对话中召回往事 |
| 7 | players_are_isolated | PASS | 不同玩家之间数据完全隔离 |
| 8 | reset_only_affects_target | PASS | 重置只清除目标玩家，其他玩家不受影响 |
| 9 | invalid_player_id_rejected | PASS | 非法玩家标识被明确拒绝 |
| 10 | db_unavailable_returns_clear_error | PASS | 数据库不可用时返回明确错误而非伪造成功 |

## 每项检查的原始返回

### 1. health_db_reachable

```json
{
  "ok": true,
  "service": "up",
  "db": {
    "ok": true,
    "host": "seekdb",
    "port": 2881,
    "user": "root@sys",
    "database": "npc_memory",
    "fts_parser": "ik"
  },
  "message": ""
}
```

### 2. schema_present

```json
{
  "database": "npc_memory",
  "tables": [
    {
      "table_name": "npc_player",
      "table_rows": 0
    },
    {
      "table_name": "npc_turn",
      "table_rows": 0
    }
  ],
  "indexes": [
    {
      "index_name": "PRIMARY",
      "table_name": "npc_player",
      "index_type": "BTREE",
      "columns": [
        "player_id",
        "id"
      ]
    },
    {
      "index_name": "idx_npc_turn_fts",
      "table_name": "npc_turn",
      "index_type": "FULLTEXT",
      "columns": [
        "__word_segment_26_1793100635378345",
        "__doc_id_1793100634944328"
      ]
    },
    {
      "index_name": "idx_npc_turn_player",
      "table_name": "npc_turn",
      "index_type": "BTREE",
      "columns": [
        "player_id",
        "turn_no"
      ]
    }
  ],
  "fts_parser": "ik"
}
```

### 3. new_player_has_no_memory

```json
{
  "player_id": "validate_player_a_193054",
  "found": false,
  "memories": []
}
```

### 4. write_turn_persisted_in_seekdb

```json
{
  "state": {
    "player_id": "validate_player_a_193054",
    "display_name": "夜归人",
    "visit_count": 1,
    "bond_score": 2,
    "chapter": "雨夜初遇",
    "favourite": "热可可",
    "running_joke": "每次来都说不急，最后都待到打烊",
    "last_input": "我想要一杯热可可",
    "last_reply": "热可可收到。你是这周第三个在雨里站着不撑伞的人。",
    "first_seen_at": "2026-10-27 11:30:55",
    "last_seen_at": "2026-10-27 11:30:55",
    "updated_at": "2026-10-27 11:30:55",
    "turn_no": 1
  },
  "stored_turn": {
    "id": 1,
    "turn_no": 1,
    "chapter": "雨夜初遇",
    "player_input": "我想要一杯热可可",
    "npc_reply": "热可可收到。你是这周第三个在雨里站着不撑伞的人。",
    "choices": [
      "问问他在淋雨的原因",
      "再点一杯热可可",
      "看看窗外的雨",
      "把伞留给他"
    ],
    "created_at": "2026-10-27 11:30:55"
  }
}
```

### 5. returning_player_recovers_state

```json
{
  "state": {
    "player_id": "validate_player_a_193054",
    "display_name": "夜归人",
    "visit_count": 2,
    "bond_score": 5,
    "chapter": "热可可与旧雨",
    "favourite": "热可可",
    "running_joke": "每次来都说不急，最后都待到打烊",
    "last_input": "热可可真的能让人不怕雨吗",
    "last_reply": "不能。但你上次说它像拥抱，我就多烧了一分钟。",
    "first_seen_at": "2026-10-27 11:30:55",
    "last_seen_at": "2026-10-27 11:30:55",
    "updated_at": "2026-10-27 11:30:55"
  },
  "memories": [
    {
      "id": 2,
      "turn_no": 2,
      "chapter": "热可可与旧雨",
      "player_input": "热可可真的能让人不怕雨吗",
      "npc_reply": "不能。但你上次说它像拥抱，我就多烧了一分钟。",
      "choices": [
        "那我明天还来",
        "把配方写给我",
        "问他为什么记得",
        "再要一杯"
      ],
      "created_at": "2026-10-27 11:30:55"
    },
    {
      "id": 1,
      "turn_no": 1,
      "chapter": "雨夜初遇",
      "player_input": "我想要一杯热可可",
      "npc_reply": "热可可收到。你是这周第三个在雨里站着不撑伞的人。",
      "choices": [
        "问问他在淋雨的原因",
        "再点一杯热可可",
        "看看窗外的雨",
        "把伞留给他"
      ],
      "created_at": "2026-10-27 11:30:55"
    }
  ]
}
```

### 6. memory_recall_uses_seekdb_fts

```json
{
  "recall_mode": "fulltext",
  "memories": [
    {
      "id": 2,
      "turn_no": 2,
      "chapter": "热可可与旧雨",
      "player_input": "热可可真的能让人不怕雨吗",
      "npc_reply": "不能。但你上次说它像拥抱，我就多烧了一分钟。",
      "choices": [
        "那我明天还来",
        "把配方写给我",
        "问他为什么记得",
        "再要一杯"
      ],
      "created_at": "2026-10-27 11:30:55"
    },
    {
      "id": 1,
      "turn_no": 1,
      "chapter": "雨夜初遇",
      "player_input": "我想要一杯热可可",
      "npc_reply": "热可可收到。你是这周第三个在雨里站着不撑伞的人。",
      "choices": [
        "问问他在淋雨的原因",
        "再点一杯热可可",
        "看看窗外的雨",
        "把伞留给他"
      ],
      "created_at": "2026-10-27 11:30:55"
    }
  ],
  "fts_parser": "ik"
}
```

### 7. players_are_isolated

```json
{
  "player_b": {
    "ok": true,
    "player_id": "validate_player_b_193054",
    "found": false,
    "is_returning": false,
    "state": null,
    "memories": [],
    "recall_mode": "recent",
    "message": ""
  },
  "player_a_still_present": true
}
```

### 8. reset_only_affects_target

```json
{
  "reset": {
    "ok": true,
    "reset": true,
    "player_id": "validate_player_a_193054",
    "deleted_turns": 2,
    "deleted_players": 1,
    "message": ""
  },
  "player_a_after": {
    "ok": true,
    "player_id": "validate_player_a_193054",
    "found": false,
    "is_returning": false,
    "state": null,
    "memories": [],
    "recall_mode": "recent",
    "message": ""
  }
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
    "message": "记忆库暂时不可用，本次没有读取到任何记忆：cannot connect to seekdb at 127.0.0.1:51579 (root@sys): root@sys: (2003, \"Can't connect to MySQL server on '127.0.0.1' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\") | root: (2003, \"Can't connect to MySQL server on '127.0.0.1' ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)\")"
  },
  "health": {
    "ok": false,
    "service": "up",
    "db": {
      "ok": false,
      "host": "127.0.0.1",
      "port": 51579,
      "user": "root@sys",
      "database": "npc_memory",
      "fts_parser": "ik"
    },
    "message": "seekdb 不可用：记忆读写全部失败"
  },
  "dead_port": 51579
}
```
