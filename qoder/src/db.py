"""seekdb 嵌入式数据库封装：连接管理、建表、读写。需用项目 .venv 的 Python 运行。"""

import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pymysql
import pylibseekdb

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data" / "seekdb.db"
DATABASE = "test"

_lock = threading.Lock()
_db = None

_CHUNKS_DDL = """CREATE TABLE IF NOT EXISTS chunks (
  id INT PRIMARY KEY AUTO_INCREMENT,
  doc_slug VARCHAR(64),
  doc_title VARCHAR(255),
  heading VARCHAR(512),
  chunk_ix INT,
  url VARCHAR(512),
  text MEDIUMTEXT,
  emb VECTOR(1024) NOT NULL,
  FULLTEXT KEY ft_chunk (text) WITH PARSER ngram
)"""

_NOTES_DDL = """CREATE TABLE IF NOT EXISTS notes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  author VARCHAR(64),
  question VARCHAR(512),
  answer MEDIUMTEXT,
  tags VARCHAR(255),
  search_text MEDIUMTEXT,
  created_at VARCHAR(64),
  FULLTEXT KEY ft_note (search_text) WITH PARSER ngram
)"""

_SEARCH_LOG_DDL = """CREATE TABLE IF NOT EXISTS search_log (
  id INT PRIMARY KEY AUTO_INCREMENT,
  query VARCHAR(512),
  result_count INT,
  elapsed_ms INT,
  created_at VARCHAR(64)
)"""


def open_db():
    """进程内单例：只 open 一次，锁保护。"""
    global _db
    with _lock:
        if _db is None:
            DB_DIR.parent.mkdir(parents=True, exist_ok=True)
            _db = pylibseekdb.open(str(DB_DIR))
        return _db


@contextmanager
def connect():
    db = open_db()
    conn = pymysql.connect(
        database=DATABASE,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        **db.connection_options(),
    )
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_CHUNKS_DDL)
            cur.execute(_NOTES_DDL)
            cur.execute(_SEARCH_LOG_DDL)


def reset() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for table in ("chunks", "notes", "search_log"):
                cur.execute(f"TRUNCATE TABLE {table}")


def _emb_str(emb) -> str:
    if isinstance(emb, str):
        return emb
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_chunks(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = ("INSERT INTO chunks "
           "(doc_slug, doc_title, heading, chunk_ix, url, text, emb) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s)")
    data = [(
        r["doc_slug"],
        r["doc_title"],
        r.get("heading") or "",
        int(r.get("chunk_ix") or 0),
        r["url"],
        r["text"],
        _emb_str(r["emb"]),
    ) for r in rows]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, data)
    return len(data)


def insert_note(author: str, question: str, answer: str, tags: str = "") -> int:
    st = (question + " " + answer + " " + tags).lower()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO notes "
                "(author, question, answer, tags, search_text, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (author, question, answer, tags, st, _now()),
            )
            return cur.lastrowid


def list_notes(limit: int = 50) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, author, question, answer, tags, search_text, created_at "
                "FROM notes ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()


def log_search(query: str, result_count: int, elapsed_ms: int) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO search_log (query, result_count, elapsed_ms, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (query, result_count, elapsed_ms, _now()),
            )
            return cur.lastrowid


def recent_searches(limit: int = 20) -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, query, result_count, elapsed_ms, created_at "
                "FROM search_log ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()


def stats() -> dict[str, int]:
    with connect() as conn:
        with conn.cursor() as cur:
            out = {}
            for table in ("chunks", "notes", "search_log"):
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
                out[table] = cur.fetchone()["n"]
            return out
