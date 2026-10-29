# src/

源码目录，放置核心业务代码：

- `text.py` — Markdown 切块、中文分词（2/3-gram）、向量化（blake2b 特征哈希）、摘要，纯标准库
- `db.py` — seekdb 封装（单例 open、pymysql 连接、三张表读写），需用 `.venv\Scripts\python.exe` 运行
- `build_index.py` — 建库脚本：`python -m src.build_index`（`--keep` 追加），产出 data/idf.json + seekdb 库 + HNSW 索引
- `retriever.py` — 检索：`python -m src.retriever "问题"`，三路召回（向量/全文/标题）+ RRF 融合 + 记忆召回
- `server.py` — 标准库 `http.server` 服务：`python -m src.server [--port 8000]`，启动预热，提供 4 个 API + 静态页面
