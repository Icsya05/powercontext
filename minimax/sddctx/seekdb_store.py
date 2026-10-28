"""seekdb access layer for the SDD context module.

seekdb (OceanBase SQL engine, MySQL wire protocol) stores the engineering
material that a development task needs:

* ``sdd_spec``  - specification entries (``R``/``B``/``A`` clauses) with their
  source file and line.
* ``sdd_code``  - code symbols (functions, classes, methods) with their source.
* ``sdd_test``  - test cases with their file and name.

Each table carries a Chinese full-text index so the context builder can ask
seekdb which material applies to a task.  The retrieval result is what reaches
MiniMax and what the module prints as "sources", so the database really does
take part in building the context.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Sequence

import pymysql
from pymysql.cursors import DictCursor

from .config import SeekDBConfig

#: Identifier used for the full-text keyword extraction.
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS sdd_spec (
        spec_id        VARCHAR(64)  NOT NULL,
        section_id     VARCHAR(64)  NOT NULL,
        kind           VARCHAR(32)  NOT NULL,
        title          VARCHAR(256) NOT NULL,
        content        TEXT         NOT NULL,
        source_path    VARCHAR(512) NOT NULL,
        source_line    INT          NOT NULL,
        doc_title      VARCHAR(256) NOT NULL DEFAULT '',
        updated_at     DATETIME     NOT NULL,
        PRIMARY KEY (spec_id, section_id)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_code (
        file_path      VARCHAR(512) NOT NULL,
        symbol         VARCHAR(128) NOT NULL,
        kind           VARCHAR(32)  NOT NULL,
        signature      VARCHAR(256) NOT NULL,
        content        TEXT         NOT NULL,
        source_path    VARCHAR(512) NOT NULL,
        source_line    INT          NOT NULL,
        updated_at     DATETIME     NOT NULL,
        PRIMARY KEY (file_path, symbol)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS sdd_test (
        test_id        VARCHAR(256) NOT NULL,
        file_path      VARCHAR(512) NOT NULL,
        name           VARCHAR(128) NOT NULL,
        target         VARCHAR(256) NOT NULL DEFAULT '',
        content        TEXT         NOT NULL,
        source_path    VARCHAR(512) NOT NULL,
        source_line    INT          NOT NULL,
        updated_at     DATETIME     NOT NULL,
        PRIMARY KEY (test_id)
    ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """,
)


class DatabaseUnavailable(RuntimeError):
    """Raised when seekdb cannot be reached or a statement fails."""


class _DefaultDatabase:
    """Sentinel telling :meth:`SeekDBStore.connect` to use the configured DB."""

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<default database>"


DEFAULT_DATABASE = _DefaultDatabase()


class SeekDBStore:
    """Thin, explicit data-access layer over seekdb."""

    def __init__(self, config: SeekDBConfig, recorder=None) -> None:
        self.config = config
        self.recorder = recorder
        self._fts_parser = "ik"

    # ------------------------------------------------------------------
    # connection handling
    # ------------------------------------------------------------------
    @contextmanager
    def connect(self, database: str | None | _DefaultDatabase = DEFAULT_DATABASE) -> Iterator[pymysql.Connection]:
        """Open a connection.

        ``database=None`` connects without selecting a schema, which is what
        creating a schema needs.  The default sentinel selects the configured
        database.
        """
        cfg = self.config
        db_name = cfg.database if isinstance(database, _DefaultDatabase) else database
        errors: list[str] = []
        conn: pymysql.Connection | None = None
        # seekdb authenticates as `user@tenant`; some deployments only accept
        # the bare user name, so fall back to it.
        for candidate in (cfg.full_user, cfg.user):
            try:
                conn = pymysql.connect(
                    host=cfg.host,
                    port=cfg.port,
                    user=candidate,
                    password=cfg.password,
                    database=db_name,
                    charset="utf8mb4",
                    cursorclass=DictCursor,
                    autocommit=True,
                    connect_timeout=cfg.connect_timeout,
                    read_timeout=cfg.read_timeout,
                    write_timeout=cfg.read_timeout,
                )
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate}: {exc}")
                conn = None
        if conn is None:
            raise DatabaseUnavailable(
                f"cannot connect to seekdb at {cfg.host}:{cfg.port} "
                f"({cfg.full_user}): " + " | ".join(errors)
            )
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, conn: pymysql.Connection, sql: str, args: Sequence[Any] = ()) -> int:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return cur.rowcount
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUnavailable(f"seekdb statement failed: {exc}") from exc

    def query(
        self, conn: pymysql.Connection, sql: str, args: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUnavailable(f"seekdb query failed: {exc}") from exc

    def _log_sql(self, sql: str, args: Sequence[Any], rows: int, mode: str) -> None:
        if self.recorder is None:
            return
        self.recorder.record(
            "seekdb.query",
            sql=" ".join(sql.split()),
            params=[str(a) for a in args],
            rows=rows,
            mode=mode,
            database=self.config.database,
        )

    # ------------------------------------------------------------------
    # schema
    # ------------------------------------------------------------------
    def ensure_database(self) -> None:
        with self.connect(database=None) as conn:
            self.execute(
                conn,
                f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` "
                "DEFAULT CHARACTER SET utf8mb4",
            )

    def ensure_schema(self) -> dict[str, Any]:
        """Create the tables and the Chinese full-text indexes."""
        with self.connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                self.execute(conn, statement)
            parser = self._ensure_fulltext_indexes(conn)
        return {"fts_parser": parser}

    def _ensure_fulltext_indexes(self, conn: pymysql.Connection) -> str:
        for table in ("sdd_spec", "sdd_code", "sdd_test"):
            index_name = f"idx_{table}_fts"
            existing = self.query(
                conn,
                "SELECT COUNT(*) AS n FROM information_schema.statistics "
                "WHERE table_schema = %s AND table_name = %s AND index_name = %s",
                (self.config.database, table, index_name),
            )
            if existing and int(existing[0]["n"]) > 0:
                continue
            for parser in ("ik", ""):
                clause = f" WITH PARSER {parser}" if parser else ""
                try:
                    self.execute(
                        conn,
                        f"CREATE FULLTEXT INDEX {index_name} ON {table} (content){clause}",
                    )
                    self._fts_parser = parser or "default"
                    break
                except DatabaseUnavailable:
                    continue
            else:
                self._fts_parser = "none"
        return self._fts_parser

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                self.query(conn, "SELECT 1 AS ok")
            return True
        except DatabaseUnavailable:
            return False

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------
    def upsert_spec(self, row: dict[str, Any]) -> None:
        sql = (
            "INSERT INTO sdd_spec (spec_id, section_id, kind, title, content, "
            "source_path, source_line, doc_title, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE kind = VALUES(kind), title = VALUES(title), "
            "content = VALUES(content), source_path = VALUES(source_path), "
            "source_line = VALUES(source_line), doc_title = VALUES(doc_title), "
            "updated_at = VALUES(updated_at)"
        )
        args = (
            row["spec_id"],
            row["section_id"],
            row["kind"],
            row["title"],
            row["content"],
            row["source_path"],
            row["source_line"],
            row.get("doc_title", ""),
            row.get("updated_at") or datetime.now(),
        )
        with self.connect() as conn:
            self.execute(conn, sql, args)
        self._log_sql(sql, args, 1, "upsert")

    def upsert_code(self, row: dict[str, Any]) -> None:
        sql = (
            "INSERT INTO sdd_code (file_path, symbol, kind, signature, content, "
            "source_path, source_line, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE kind = VALUES(kind), signature = VALUES(signature), "
            "content = VALUES(content), source_path = VALUES(source_path), "
            "source_line = VALUES(source_line), updated_at = VALUES(updated_at)"
        )
        args = (
            row["file_path"],
            row["symbol"],
            row["kind"],
            row["signature"],
            row["content"],
            row["source_path"],
            row["source_line"],
            row.get("updated_at") or datetime.now(),
        )
        with self.connect() as conn:
            self.execute(conn, sql, args)
        self._log_sql(sql, args, 1, "upsert")

    def upsert_test(self, row: dict[str, Any]) -> None:
        sql = (
            "INSERT INTO sdd_test (test_id, file_path, name, target, content, "
            "source_path, source_line, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE file_path = VALUES(file_path), name = VALUES(name), "
            "target = VALUES(target), content = VALUES(content), "
            "source_path = VALUES(source_path), source_line = VALUES(source_line), "
            "updated_at = VALUES(updated_at)"
        )
        args = (
            row["test_id"],
            row["file_path"],
            row["name"],
            row.get("target", ""),
            row["content"],
            row["source_path"],
            row["source_line"],
            row.get("updated_at") or datetime.now(),
        )
        with self.connect() as conn:
            self.execute(conn, sql, args)
        self._log_sql(sql, args, 1, "upsert")

    def delete_source(self, source_path: str) -> int:
        """Drop every row that came from one file (used when re-importing)."""
        removed = 0
        with self.connect() as conn:
            for table in ("sdd_spec", "sdd_code", "sdd_test"):
                removed += self.execute(
                    conn, f"DELETE FROM {table} WHERE source_path = %s", (source_path,)
                )
        self._log_sql("DELETE ... WHERE source_path = %s", (source_path,), removed, "delete")
        return removed

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    @staticmethod
    def keyword(text: str, limit: int = 12) -> str:
        """Reduce free text to a full-text keyword string."""
        tokens = [t for t in _TOKEN_RE.findall(text or "") if t]
        if not tokens:
            return ""
        seen: list[str] = []
        for token in tokens:
            if token not in seen:
                seen.append(token)
        return " ".join(seen[:limit])

    def _search(
        self,
        table: str,
        keyword: str,
        limit: int,
        extra_sql: str = "",
        extra_args: Sequence[Any] = (),
    ) -> tuple[list[dict[str, Any]], str]:
        """Full-text search with a LIKE fallback."""
        mode = "fulltext"
        if keyword and self._fts_parser not in ("none", ""):
            sql = (
                f"SELECT * FROM {table} WHERE MATCH(content) AGAINST (%s) "
                f"{extra_sql} ORDER BY updated_at DESC LIMIT %s"
            )
            args = [keyword, *extra_args, int(limit)]
            try:
                with self.connect() as conn:
                    rows = self.query(conn, sql, args)
                self._log_sql(sql, args, len(rows), mode)
                if rows:
                    return rows, mode
            except DatabaseUnavailable:
                mode = "fulltext-failed"

        mode = "like"
        like = f"%{keyword[:40]}%" if keyword else "%"
        sql = f"SELECT * FROM {table} WHERE content LIKE %s {extra_sql} ORDER BY updated_at DESC LIMIT %s"
        args = [like, *extra_args, int(limit)]
        with self.connect() as conn:
            rows = self.query(conn, sql, args)
        self._log_sql(sql, args, len(rows), mode)
        return rows, mode

    def search_specs(self, keyword: str, limit: int = 12) -> tuple[list[dict[str, Any]], str]:
        return self._search("sdd_spec", keyword, limit)

    def search_code(self, keyword: str, limit: int = 12) -> tuple[list[dict[str, Any]], str]:
        return self._search("sdd_code", keyword, limit)

    def search_tests(self, keyword: str, limit: int = 12) -> tuple[list[dict[str, Any]], str]:
        return self._search("sdd_test", keyword, limit)

    def get_spec_sections(self, spec_id: str) -> list[dict[str, Any]]:
        sql = (
            "SELECT * FROM sdd_spec WHERE spec_id = %s ORDER BY section_id"
        )
        with self.connect() as conn:
            rows = self.query(conn, sql, (spec_id,))
        self._log_sql(sql, (spec_id,), len(rows), "select")
        return rows

    def get_spec(self, spec_id: str, section_id: str) -> dict[str, Any] | None:
        sql = "SELECT * FROM sdd_spec WHERE spec_id = %s AND section_id = %s"
        with self.connect() as conn:
            rows = self.query(conn, sql, (spec_id, section_id))
        self._log_sql(sql, (spec_id, section_id), len(rows), "select")
        return rows[0] if rows else None

    def get_code(self, file_path: str, symbol: str) -> dict[str, Any] | None:
        sql = "SELECT * FROM sdd_code WHERE file_path = %s AND symbol = %s"
        with self.connect() as conn:
            rows = self.query(conn, sql, (file_path, symbol))
        self._log_sql(sql, (file_path, symbol), len(rows), "select")
        return rows[0] if rows else None

    def get_code_of_file(self, file_path: str) -> list[dict[str, Any]]:
        """Every indexed symbol of one file."""
        sql = "SELECT * FROM sdd_code WHERE file_path = %s ORDER BY source_line"
        with self.connect() as conn:
            rows = self.query(conn, sql, (file_path,))
        self._log_sql(sql, (file_path,), len(rows), "select")
        return rows

    def get_tests_of_file(self, file_path: str) -> list[dict[str, Any]]:
        """Every indexed test case of one file."""
        sql = "SELECT * FROM sdd_test WHERE file_path = %s ORDER BY source_line"
        with self.connect() as conn:
            rows = self.query(conn, sql, (file_path,))
        self._log_sql(sql, (file_path,), len(rows), "select")
        return rows

    def counts(self) -> dict[str, int]:
        sql = (
            "SELECT (SELECT COUNT(*) FROM sdd_spec) AS specs, "
            "(SELECT COUNT(*) FROM sdd_code) AS code, "
            "(SELECT COUNT(*) FROM sdd_test) AS tests"
        )
        with self.connect() as conn:
            rows = self.query(conn, sql)
        self._log_sql(sql, (), len(rows), "select")
        row = rows[0] if rows else {}
        return {key: int(row.get(key, 0)) for key in ("specs", "code", "tests")}

    def list_spec_ids(self) -> list[str]:
        sql = "SELECT DISTINCT spec_id FROM sdd_spec ORDER BY spec_id"
        with self.connect() as conn:
            rows = self.query(conn, sql)
        self._log_sql(sql, (), len(rows), "select")
        return [row["spec_id"] for row in rows]
