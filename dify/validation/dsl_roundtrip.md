# Dify DSL 往返验证记录（导入 → 发布 → 导出 → 重导入 → 再导出）

- 运行时间：2026-10-27T22:04:28
- 结果：**7 通过 / 0 失败**

| # | 检查项 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | console_login | PASS | 登录 Dify 控制台 |
| 2 | dsl_import | PASS | 把 workflow.yml 导入 Dify |
| 3 | publish_and_enable_api | PASS | 发布工作流并开启 API 访问 |
| 4 | dsl_export | PASS | 从 Dify 导出 DSL |
| 5 | export_matches_source | PASS | 导出的 DSL 与源文件图结构一致 |
| 6 | dsl_reimport_clean_app | PASS | 把导出的 DSL 导入一个干净的新应用 |
| 7 | reimported_export_identical | PASS | 重新导入后再导出与第一次导出逐字节一致 |

## 每项检查的原始返回

### 1. console_login

```json
{
  "email": "admin@midnight-store.local",
  "csrf": true
}
```

### 2. dsl_import

```json
{
  "app_id": "e88c96eb-a7e2-42c1-aefc-840615502830",
  "dsl_bytes": 29271
}
```

### 3. publish_and_enable_api

```json
{
  "published": null,
  "api_enabled": null
}
```

### 4. dsl_export

```json
{
  "export_bytes": 29271,
  "dsl_version": "0.7.0",
  "app_mode": "workflow",
  "nodes": 13,
  "edges": 12
}
```

### 5. export_matches_source

```json
{
  "source_nodes": 13,
  "source_edges": 12,
  "exported_nodes": 13,
  "exported_edges": 12,
  "llm_node": [
    {
      "id": "llm_ache",
      "type": "llm",
      "title": "阿澈回应",
      "model_provider": "langgenius/openai_api_compatible/openai_api_compatible",
      "model_name": "MiniMax-M3",
      "url": null,
      "method": null
    }
  ],
  "http_nodes": [
    {
      "id": "http_read_state",
      "type": "http-request",
      "title": "读取记忆",
      "model_provider": null,
      "model_name": null,
      "url": "http://host.docker.internal:8077/api/state",
      "method": "post"
    },
    {
      "id": "http_save_turn",
      "type": "http-request",
      "title": "写回记忆",
      "model_provider": null,
      "model_name": null,
      "url": "http://host.docker.internal:8077/api/turn",
      "method": "post"
    }
  ]
}
```

### 6. dsl_reimport_clean_app

```json
{
  "new_app_id": "e00b58e1-6a2e-4d3e-bec8-cc3df4176cca"
}
```

### 7. reimported_export_identical

```json
{
  "identical": true,
  "bytes": 29271,
  "app_id": "e00b58e1-6a2e-4d3e-bec8-cc3df4176cca"
}
```
