# Dify 工作流真实验证记录

- 运行时间：2026-10-27T22:03:44
- 结果：**16 通过 / 0 失败**

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | console_login | PASS | 登录 Dify 控制台 |
| 2 | dsl_import | PASS | 把 workflow.yml 导入 Dify |
| 3 | publish_and_enable_api | PASS | 发布工作流并开启 API 访问 |
| 4 | app_api_key | PASS | 取得应用的 API Key |
| 5 | run_new_player | PASS | 新玩家跑通一次完整对话 |
| 6 | state_written_to_seekdb | PASS | 这一轮确实写进了 seekdb |
| 7 | run_returning_player_new_conversation | PASS | 同一玩家在新会话里再跑一次 |
| 8 | state_recovered_across_sessions | PASS | 新会话里记忆被恢复（到店次数 +1） |
| 9 | run_second_player | PASS | 另一个玩家跑一次（隔离） |
| 10 | players_isolated | PASS | 两个玩家在数据库里互不干扰 |
| 11 | run_reset | PASS | 执行重置 |
| 12 | reset_cleared_rows | PASS | 重置后数据库里只剩另一个玩家 |
| 13 | dsl_export | PASS | 从运行中的应用导出 DSL |
| 14 | dsl_reimport_clean_app | PASS | 把导出的 DSL 导入一个干净的新应用 |
| 15 | reimported_workflow_runs | PASS | 重新导入后的工作流依然能跑通并写库 |
| 16 | node_executions_recorded | PASS | 控制台记录了节点级执行轨迹 |

## 每项检查的原始返回

### 1. console_login

```json
{
  "email": "admin@midnight-store.local",
  "csrf_received": true
}
```

### 2. dsl_import

```json
{
  "app_id": "94b5bf14-88ea-4a31-9b10-87d67efca493",
  "dsl_bytes": 28976
}
```

### 3. publish_and_enable_api

```json
{
  "published": null,
  "api_enabled": null
}
```

### 4. app_api_key

```json
{
  "app_api_key_prefix": "app-E0Q9..."
}
```

### 5. run_new_player

```json
{
  "outputs": {
    "answer": "门上的风铃被撞得乱响，湿冷的风贴着地砖钻进来，货架上的关东煮正咕嘟冒泡。*我抬眼看了看你，把最后一罐热可可往暖柜里推了推*“第一次来就赶上这种雨，算你倒霉，也算这盏灯还亮着的证明。先擦擦头发，别站在风口里——想喝热的，还是吃点关东煮？”\n\n你可以：\n- 来一罐热可可\n- 给我煮份关东煮\n- 借条毛巾擦头发\n- 雨什么时候会停\n\n（已记在账本里：第 1 次到店 ｜ 羁绊 1 ｜ 章节「暴雨初遇」）"
  },
  "status": "succeeded",
  "elapsed_time": 11.876591,
  "total_steps": 11
}
```

### 6. state_written_to_seekdb

```json
{
  "player_id": "wf_player_a_220239",
  "visit_count": 1,
  "bond_score": 1,
  "chapter": "暴雨初遇",
  "favourite": "",
  "memories": 1,
  "recall_mode": "recent"
}
```

### 7. run_returning_player_new_conversation

```json
{
  "outputs": {
    "answer": "……夜班的灯管闪了一下，阿澈什么也没说。\n\n\n（已记在账本里：第 2 次到店 ｜ 羁绊 1 ｜ 章节「雨夜初遇」）"
  },
  "status": "succeeded",
  "elapsed_time": 15.904014,
  "total_steps": 11
}
```

### 8. state_recovered_across_sessions

```json
{
  "player_id": "wf_player_a_220239",
  "visit_count": 2,
  "bond_score": 1,
  "chapter": "雨夜初遇",
  "favourite": "",
  "memories": 2,
  "recall_mode": "recent"
}
```

### 9. run_second_player

```json
{
  "outputs": {
    "answer": "*门上的风铃被雨声撞得乱响，我放下抹布，弯腰把门口的湿伞往里收了收。*“第一次见你。外套先别急着脱，坐这边，暖气还足。”我推过一卷干纸巾，又指了指关东煮的蒸汽，“热可可只剩最后三罐，想喝就给你留一罐。”\n\n你可以：\n- 擦干外套再坐下\n- 要一罐热可可\n- 看看关东煮有什么\n- 问剩下的热可可多少钱\n\n（已记在账本里：第 1 次到店 ｜ 羁绊 1 ｜ 章节「雨夜初遇」）"
  },
  "status": "succeeded",
  "elapsed_time": 13.496828,
  "total_steps": 11
}
```

### 10. players_isolated

```json
{
  "player_a_visit_count": 2,
  "player_b_visit_count": 1,
  "player_b_memories": 1
}
```

### 11. run_reset

```json
{
  "outputs": {
    "answer": "🧾 会员卡 wf_player_a_220239 已注销，阿澈把记着你的那几页撕掉了。\n\n{\"reply\":\"*我把热可可罐放回暖柜，关东煮的蒸汽蒙住玻璃，门外的雨敲着檐沟*“好，不劝你。注销前我核对了一下：你上次说‘还是热可可吧，跟上次一样’，那晚灯管正好闪了一下。会员卡作废，账本这行也擦掉，今晚不收你钱。伞在"
  },
  "status": "succeeded",
  "elapsed_time": 13.604558,
  "total_steps": 11
}
```

### 12. reset_cleared_rows

```json
{
  "reset_player_found": false,
  "other_player_found": true
}
```

### 13. dsl_export

```json
{
  "exported_bytes": 29271,
  "saved_to": "D:\\ZhuYijing\\Documents\\minimax工作文件夹\\powercontext\\dify\\validation\\dsl_exported.yml"
}
```

### 14. dsl_reimport_clean_app

```json
{
  "new_app_id": "8858f3bd-c869-4277-8093-6a331a81f856"
}
```

### 15. reimported_workflow_runs

```json
{
  "reimport_app_id": "8858f3bd-c869-4277-8093-6a331a81f856",
  "outputs": {
    "answer": "*顶灯白得有点晃，关东煮的汤翻滚着萝卜和鱼丸，门外雨点砸在遮雨棚上，噼啪作响。* “第一次来？鞋尖都湿了。毛巾在收银台左边，先擦一下。今晚热可可只剩三罐，你要是淋久了，我给你留一罐热的。先喝点东西暖暖，别逞强。”\n\n你可以：\n- 借毛巾擦头发\n- 点一份关东煮\n- 喝罐热可可\n- 看看关东煮还剩什么\n\n（已记在账本里：第 1 次到店 ｜ 羁绊 1 ｜ 章节「雨夜初遇」）"
  },
  "state": {
    "player_id": "wf_reimport_220239",
    "visit_count": 1,
    "bond_score": 1,
    "chapter": "雨夜初遇",
    "favourite": "",
    "memories": 1,
    "recall_mode": "recent"
  }
}
```

### 16. node_executions_recorded

```json
{
  "runs": 0,
  "note": "详见 workflow_checks.md 的运行记录"
}
```
