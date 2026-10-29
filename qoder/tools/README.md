# tools/

脚本目录，放置开发/运维用命令行脚本：

- `fetch_docs.py` — 从语雀抓取 OceanBase 大赛官方文档到 `data/docs/`
  用法：`python tools/fetch_docs.py`
- `eval_retrieval.py` — 检索回归评测：`python tools/eval_retrieval.py [--k 5]`，
  基于 data/eval_questions.json 打印 Recall@1/@3/@5、耗时中位数与未命中题目名次
- `inspect_db.py` — 体检库：`python tools/inspect_db.py`，打印表、各表索引类型
  （确认 VECTOR / FULLTEXT 索引真的建上了）、行数与最近查询
