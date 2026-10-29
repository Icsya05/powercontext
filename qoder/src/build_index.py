"""建库：读语料 → 切块 → 分词 → IDF → 向量化 → 入库 → 建 HNSW 向量索引。

用法（项目根目录，需用 .venv 的 Python）：
    .\\.venv\\Scripts\\python.exe -m src.build_index          # 清空重建
    .\\.venv\\Scripts\\python.exe -m src.build_index --keep   # 追加不清空
"""

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from src import db as db_mod
from src.db import DB_DIR, connect, ensure_schema, insert_chunks, stats
from src.text import build_idf, split_into_chunks, vectorize

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
INDEX_PATH = DOCS_DIR / "index.json"
IDF_PATH = ROOT / "data" / "idf.json"

BATCH_SIZE = 50
CARD_MARK = "此处为语雀卡片"
MIN_EFFECTIVE_CHARS = 120
HNSW_INDEX = "idx_chunk_emb"
HNSW_DDL = (f"CREATE VECTOR INDEX {HNSW_INDEX} ON chunks(emb) "
            "WITH (distance=l2, type=hnsw)")


def log(msg: str = "") -> None:
    print(msg, flush=True)


def effective_chars(md: str) -> int:
    """去掉标题行、Markdown 链接和 HTML 标签后的非空白字符数。"""
    text = re.sub(r"^#{1,6}\s+.*$", "", md, flags=re.M)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return len(re.sub(r"\s+", "", text))


def ensure_hnsw() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW INDEX FROM chunks")
            if any(r.get("Key_name") == HNSW_INDEX for r in cur.fetchall()):
                log("HNSW 向量索引已存在，跳过")
                return
            cur.execute(HNSW_DDL)
            log("HNSW 向量索引已创建")


def wipe_db_dir() -> None:
    """清空重建必须删整个库目录，不能只 TRUNCATE 表。

    实测：TRUNCATE 之后 seekdb 全文索引里的倒排条目并没有被清掉，原地重建几次后
    同一个词被重复计入，MATCH ... AGAINST 的打分整体虚高——同一道题在重建过 3 次的库上
    全文路 top1 是 15.7 分、在干净库上只有 3.4 分，名次从第 1 掉到第 5，
    28 题 R@1 因此从 89.3% 虚涨到 96.4%。OPTIMIZE TABLE 也清不掉。
    所以重建一律从空目录开始，保证结果可复现。
    """
    db_mod._db = None  # 本进程若已 open 过，先丢掉句柄，否则 Windows 上删不掉目录
    if DB_DIR.exists():
        shutil.rmtree(DB_DIR)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="建库：语料 → 切块 → 向量化 → seekdb")
    parser.add_argument("--keep", action="store_true", help="追加模式，不清空已有数据")
    args = parser.parse_args()

    t0 = time.time()
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    docs = index["docs"]
    log(f"index.json 共 {len(docs)} 篇文档")

    all_chunks = []
    skipped: list[tuple[str, str]] = []
    processed = 0
    for d in docs:
        path = DOCS_DIR / f"{d['slug']}.md"
        if not path.exists():
            skipped.append((d["title"], "文件缺失"))
            continue
        md = path.read_text(encoding="utf-8")
        eff = effective_chars(md)
        if CARD_MARK in md and eff < MIN_EFFECTIVE_CHARS:
            skipped.append((d["title"], f"占位页，有效字数 {eff}"))
            continue
        all_chunks.extend(split_into_chunks(md, d["slug"], d["title"], d["url"]))
        processed += 1

    idf = build_idf([c.tokens for c in all_chunks])
    IDF_PATH.write_text(json.dumps(idf, ensure_ascii=False), encoding="utf-8")
    log(f"切块 {len(all_chunks)} 个，词表 {len(idf)} 个，IDF 已写入 {IDF_PATH.name}")

    if args.keep:
        ensure_schema()
        log("--keep 追加模式，不清空已有数据")
    else:
        wipe_db_dir()
        ensure_schema()
        log("已删除库目录并重建，全文索引从零开始")

    rows = [{
        "doc_slug": c.doc_slug,
        "doc_title": c.doc_title,
        "heading": c.heading,
        "chunk_ix": c.index,
        "url": c.url,
        "text": c.text,
        "emb": vectorize(c.tokens, idf),
    } for c in all_chunks]
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        insert_chunks(rows[i:i + BATCH_SIZE])
        log(f"  已写入 {min(i + BATCH_SIZE, total)}/{total} 条")

    # 全部插入完再建向量索引，比边插边建快得多
    ensure_hnsw()

    log("\n===== 建库完成 =====")
    log(f"处理 {processed} 篇，跳过 {len(skipped)} 篇")
    for title, reason in skipped:
        log(f"  - {title}（{reason}）")
    log(f"切块 {len(all_chunks)} 个，词表 {len(idf)} 个")
    log(f"耗时 {time.time() - t0:.1f} 秒")
    log(f"库内行数: {stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
