"""SeekDB access layer for the Midnight Convenience Store NPC memory.

The NPC's long-term memory lives in seekdb (OceanBase SQL engine, MySQL wire
protocol).  Two tables are used:

* ``npc_player``  - one row per player: the aggregate state the NPC "knows".
* ``npc_turn``    - the append-only dialogue log, with a Chinese full-text
  index so past conversations can be recalled with ``MATCH ... AGAINST``.

Connections use the official seekdb server convention documented by the
``pyseekdb`` SDK: ``user@tenant`` as the MySQL user, port 2881, utf8mb4.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Sequence

import pymysql
from pymysql.cursors import DictCursor

#: Player identifiers are used verbatim as primary keys and as the
#: ``player_id`` filter of every query, so they are restricted to a safe
#: character set instead of being escaped into SQL.
PLAYER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

MAX_REPLY_CHARS = 1000
MAX_INPUT_CHARS = 500
MAX_CHOICE_CHARS = 120
MAX_CHOICES = 4
MAX_BOND_DELTA = 10


class DatabaseUnavailable(RuntimeError):
    """Raised when seekdb cannot be reached or a statement fails."""


class InvalidPlayerId(ValueError):
    """Raised when a player identifier does not satisfy :data:`PLAYER_ID_RE`."""


@dataclass(frozen=True)
class StoreConfig:
    """Connection settings, all overridable through environment variables.

    The defaults are resolved when an instance is created, not when this
    module is imported: the deploy scripts load ``dify/.env`` *after* the
    import, so binding the environment at class-creation time would silently
    discard every value from the env file.
    """

    host: str = field(default_factory=lambda: os.getenv("SEEKDB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("SEEKDB_PORT", "2881")))
    user: str = field(default_factory=lambda: os.getenv("SEEKDB_USER", "root"))
    # The compose file maps SEEKDB_ROOT_PASSWORD onto SEEKDB_PASSWORD for the
    # container; the host-side scripts read the env file directly, so accept
    # either name for the same secret.
    password: str = field(
        default_factory=lambda: os.getenv("SEEKDB_PASSWORD")
        or os.getenv("SEEKDB_ROOT_PASSWORD", "")
    )
    tenant: str = field(default_factory=lambda: os.getenv("SEEKDB_TENANT", "sys"))
    database: str = field(default_factory=lambda: os.getenv("SEEKDB_DATABASE", "npc_memory"))
    connect_timeout: int = field(
        default_factory=lambda: int(os.getenv("SEEKDB_CONNECT_TIMEOUT", "5"))
    )
    read_timeout: int = field(default_factory=lambda: int(os.getenv("SEEKDB_READ_TIMEOUT", "15")))

    @property
    def full_user(self) -> str:
        """seekdb server authenticates as ``user@tenant``."""
        return f"{self.user}@{self.tenant}"


def validate_player_id(player_id: str) -> str:
    """Return a validated player id or raise :class:`InvalidPlayerId`."""
    if not isinstance(player_id, str):
        raise InvalidPlayerId("player_id must be a string")
    candidate = player_id.strip()
    if not PLAYER_ID_RE.match(candidate):
        raise InvalidPlayerId(
            "player_id must be 1-64 characters of letters, digits, '-' or '_'"
        )
    return candidate


def _clamp_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value)[:limit]


class SeekDbStore:
    """Thin, explicit data-access layer over seekdb."""

    def __init__(self, config: StoreConfig | None = None) -> None:
        self.config = config or StoreConfig()
        self._fts_parser = "ik"

    # ------------------------------------------------------------------
    # connection handling
    # ------------------------------------------------------------------
    @contextmanager
    def _connect(self, database: str | None = None) -> Iterator[pymysql.Connection]:
        cfg = self.config
        db_name = database if database is not None else cfg.database
        # seekdb authenticates as `user@tenant` (the convention used by the
        # official pyseekdb SDK).  Some deployments only accept the bare user
        # name, so fall back to it when the tenant-qualified form is rejected.
        errors: list[str] = []
        conn: pymysql.Connection | None = None
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
            except Exception as exc:  # noqa: BLE001 - surfaced as a typed error
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

    def _execute(self, conn: pymysql.Connection, sql: str, args: Sequence[Any] = ()) -> int:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return cur.rowcount
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUnavailable(f"seekdb statement failed: {exc}") from exc

    def _query(
        self, conn: pymysql.Connection, sql: str, args: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUnavailable(f"seekdb query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # schema
    # ------------------------------------------------------------------
    def ensure_database(self) -> None:
        """Create the application database when it does not exist yet."""
        with self._connect(database=None) as conn:
            self._execute(
                conn,
                f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` "
                "DEFAULT CHARACTER SET utf8mb4",
            )

    def ensure_schema(self) -> dict[str, Any]:
        """Create the tables and indexes used by the memory service.

        The Chinese full-text index is created with the ``ik`` parser.  If the
        running seekdb build does not provide that parser the index is created
        with the default parser instead; recall then degrades to the default
        tokenizer, which is reported back to the caller.
        """
        with self._connect() as conn:
            self._execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS npc_player (
                    player_id     VARCHAR(64)  NOT NULL,
                    display_name  VARCHAR(64)  NOT NULL DEFAULT '',
                    visit_count   INT          NOT NULL DEFAULT 0,
                    bond_score    INT          NOT NULL DEFAULT 0,
                    chapter       VARCHAR(64)  NOT NULL DEFAULT '雨夜初遇',
                    favourite     VARCHAR(128) NOT NULL DEFAULT '',
                    running_joke  VARCHAR(256) NOT NULL DEFAULT '',
                    last_input    VARCHAR(512) NOT NULL DEFAULT '',
                    last_reply    VARCHAR(1000) NOT NULL DEFAULT '',
                    first_seen_at DATETIME     NOT NULL,
                    last_seen_at  DATETIME     NOT NULL,
                    updated_at    DATETIME     NOT NULL,
                    PRIMARY KEY (player_id)
                ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
                """,
            )
            self._execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS npc_turn (
                    id           BIGINT       NOT NULL AUTO_INCREMENT,
                    player_id    VARCHAR(64)  NOT NULL,
                    turn_no      INT          NOT NULL,
                    chapter      VARCHAR(64)  NOT NULL DEFAULT '',
                    player_input VARCHAR(500) NOT NULL DEFAULT '',
                    npc_reply    VARCHAR(1000) NOT NULL DEFAULT '',
                    choices      VARCHAR(512) NOT NULL DEFAULT '',
                    content      TEXT         NOT NULL,
                    created_at   DATETIME     NOT NULL,
                    PRIMARY KEY (id),
                    KEY idx_npc_turn_player (player_id, turn_no)
                ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
                """,
            )
            parser = self._ensure_fulltext_index(conn)
        return {"fts_parser": parser}

    def _ensure_fulltext_index(self, conn: pymysql.Connection) -> str:
        existing = self._query(
            conn,
            "SELECT COUNT(*) AS n FROM information_schema.statistics "
            "WHERE table_schema = %s AND table_name = 'npc_turn' "
            "AND index_name = 'idx_npc_turn_fts'",
            (self.config.database,),
        )
        if existing and int(existing[0]["n"]) > 0:
            return self._fts_parser

        for parser in ("ik", ""):
            clause = f" WITH PARSER {parser}" if parser else ""
            try:
                self._execute(
                    conn,
                    f"CREATE FULLTEXT INDEX idx_npc_turn_fts ON npc_turn (content){clause}",
                )
                self._fts_parser = parser or "default"
                return self._fts_parser
            except DatabaseUnavailable:
                continue
        # Full-text search is optional: recall falls back to a LIKE scan.
        self._fts_parser = "none"
        return self._fts_parser

    def ping(self) -> bool:
        """Return ``True`` when seekdb answers a trivial statement."""
        try:
            with self._connect() as conn:
                self._query(conn, "SELECT 1 AS ok")
            return True
        except DatabaseUnavailable:
            return False

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def get_player(self, player_id: str) -> dict[str, Any] | None:
        player_id = validate_player_id(player_id)
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT player_id, display_name, visit_count, bond_score, chapter, "
                "favourite, running_joke, last_input, last_reply, first_seen_at, "
                "last_seen_at, updated_at FROM npc_player WHERE player_id = %s",
                (player_id,),
            )
        if not rows:
            return None
        row = dict(rows[0])
        for key in ("first_seen_at", "last_seen_at", "updated_at"):
            if isinstance(row.get(key), datetime):
                row[key] = row[key].isoformat(sep=" ", timespec="seconds")
        return row

    def count_turns(self, player_id: str) -> int:
        player_id = validate_player_id(player_id)
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT COUNT(*) AS n FROM npc_turn WHERE player_id = %s",
                (player_id,),
            )
        return int(rows[0]["n"]) if rows else 0

    def recent_turns(self, player_id: str, limit: int = 5) -> list[dict[str, Any]]:
        player_id = validate_player_id(player_id)
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT id, turn_no, chapter, player_input, npc_reply, choices, created_at "
                "FROM npc_turn WHERE player_id = %s ORDER BY turn_no DESC LIMIT %s",
                (player_id, int(limit)),
            )
        return [self._serialize_turn(row) for row in rows]

    def recall_memories(
        self, player_id: str, query_text: str, limit: int = 4
    ) -> tuple[list[dict[str, Any]], str]:
        """Recall past turns of ``player_id`` that match ``query_text``.

        Returns the recalled turns together with the strategy that produced
        them (``"fulltext"``, ``"fulltext-boolean"`` or ``"like"``), so the
        evidence trail shows which seekdb capability was actually exercised.
        """
        player_id = validate_player_id(player_id)
        query_text = (query_text or "").strip()
        if not query_text:
            return self.recent_turns(player_id, limit=limit), "recent"

        keyword = self._fts_keyword(query_text)
        if keyword and self._fts_parser not in ("none", ""):
            for mode, sql in (
                (
                    "fulltext",
                    "SELECT id, turn_no, chapter, player_input, npc_reply, choices, created_at "
                    "FROM npc_turn WHERE player_id = %s AND MATCH(content) AGAINST (%s) "
                    "ORDER BY turn_no DESC LIMIT %s",
                ),
                (
                    "fulltext-boolean",
                    "SELECT id, turn_no, chapter, player_input, npc_reply, choices, created_at "
                    "FROM npc_turn WHERE player_id = %s AND MATCH(content) AGAINST (%s IN BOOLEAN MODE) "
                    "ORDER BY turn_no DESC LIMIT %s",
                ),
            ):
                try:
                    with self._connect() as conn:
                        rows = self._query(conn, sql, (player_id, keyword, int(limit)))
                except DatabaseUnavailable:
                    continue
                if rows:
                    return [self._serialize_turn(row) for row in rows], mode

        like = f"%{query_text[:40]}%"
        with self._connect() as conn:
            rows = self._query(
                conn,
                "SELECT id, turn_no, chapter, player_input, npc_reply, choices, created_at "
                "FROM npc_turn WHERE player_id = %s AND content LIKE %s "
                "ORDER BY turn_no DESC LIMIT %s",
                (player_id, like, int(limit)),
            )
        if rows:
            return [self._serialize_turn(row) for row in rows], "like"
        return self.recent_turns(player_id, limit=limit), "recent"

    @staticmethod
    def _fts_keyword(query_text: str) -> str:
        """Reduce free text to something the full-text parser can use."""
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query_text, flags=re.UNICODE)
        tokens = [t for t in tokens if t]
        if not tokens:
            return ""
        # Single CJK characters are too noisy for the tokenizer; keep the
        # longest run as one keyword.
        return " ".join(tokens[:6])

    @staticmethod
    def _serialize_turn(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].isoformat(sep=" ", timespec="seconds")
        if out.get("choices"):
            try:
                out["choices"] = json.loads(out["choices"])
            except (TypeError, ValueError):
                out["choices"] = []
        else:
            out["choices"] = []
        return out

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------
    def save_turn(
        self,
        player_id: str,
        *,
        player_input: str,
        npc_reply: str,
        choices: Sequence[str],
        chapter: str,
        bond_delta: int,
        favourite: str,
        running_joke: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        """Persist one NPC turn and merge it into the player's aggregate state."""
        player_id = validate_player_id(player_id)
        player_input = _clamp_text(player_input, MAX_INPUT_CHARS)
        npc_reply = _clamp_text(npc_reply, MAX_REPLY_CHARS)
        chapter = _clamp_text(chapter, 64) or "雨夜初遇"
        favourite = _clamp_text(favourite, 128)
        running_joke = _clamp_text(running_joke, 256)
        display_name = _clamp_text(display_name, 64)
        clean_choices = [
            _clamp_text(choice, MAX_CHOICE_CHARS) for choice in list(choices)[:MAX_CHOICES]
        ]
        clean_choices = [choice for choice in clean_choices if choice]
        try:
            delta = max(-MAX_BOND_DELTA, min(MAX_BOND_DELTA, int(bond_delta)))
        except (TypeError, ValueError):
            delta = 0

        now = datetime.now()
        content = f"{player_input} {npc_reply}".strip()

        with self._connect() as conn:
            turn_no = int(
                self._query(
                    conn,
                    "SELECT COUNT(*) AS n FROM npc_turn WHERE player_id = %s",
                    (player_id,),
                )[0]["n"]
            ) + 1

            self._execute(
                conn,
                "INSERT INTO npc_turn (player_id, turn_no, chapter, player_input, npc_reply, "
                "choices, content, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    player_id,
                    turn_no,
                    chapter,
                    player_input,
                    npc_reply,
                    json.dumps(clean_choices, ensure_ascii=False),
                    content,
                    now,
                ),
            )

            existing = self._query(
                conn,
                "SELECT visit_count, bond_score, first_seen_at FROM npc_player "
                "WHERE player_id = %s",
                (player_id,),
            )
            if existing:
                visit_count = int(existing[0]["visit_count"]) + 1
                bond_score = int(existing[0]["bond_score"]) + delta
                first_seen_at = existing[0]["first_seen_at"]
            else:
                visit_count = 1
                bond_score = delta
                first_seen_at = now

            self._execute(
                conn,
                "INSERT INTO npc_player (player_id, display_name, visit_count, bond_score, "
                "chapter, favourite, running_joke, last_input, last_reply, first_seen_at, "
                "last_seen_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE display_name = VALUES(display_name), "
                "visit_count = VALUES(visit_count), bond_score = VALUES(bond_score), "
                "chapter = VALUES(chapter), favourite = VALUES(favourite), "
                "running_joke = VALUES(running_joke), last_input = VALUES(last_input), "
                "last_reply = VALUES(last_reply), last_seen_at = VALUES(last_seen_at), "
                "updated_at = VALUES(updated_at)",
                (
                    player_id,
                    display_name,
                    visit_count,
                    bond_score,
                    chapter,
                    favourite,
                    running_joke,
                    player_input,
                    npc_reply,
                    first_seen_at,
                    now,
                    now,
                ),
            )

        state = self.get_player(player_id)
        assert state is not None  # just written above
        state["turn_no"] = turn_no
        return state

    def reset_player(self, player_id: str) -> dict[str, Any]:
        """Delete every trace of ``player_id``.  Other players are untouched."""
        player_id = validate_player_id(player_id)
        with self._connect() as conn:
            turns = self._execute(conn, "DELETE FROM npc_turn WHERE player_id = %s", (player_id,))
            players = self._execute(conn, "DELETE FROM npc_player WHERE player_id = %s", (player_id,))
        return {"player_id": player_id, "deleted_turns": turns, "deleted_players": players}

    def list_players(self) -> list[str]:
        """Return every known player id (used by the validation scripts)."""
        with self._connect() as conn:
            rows = self._query(conn, "SELECT player_id FROM npc_player ORDER BY player_id")
        return [row["player_id"] for row in rows]

    def describe_schema(self) -> dict[str, Any]:
        """Describe the tables and indexes actually present in seekdb.

        Used by the validation run so the evidence shows the real schema and
        the real full-text index, not just the service's intent.
        """
        with self._connect() as conn:
            tables = self._query(
                conn,
                "SELECT table_name, table_rows FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name IN ('npc_player', 'npc_turn') "
                "ORDER BY table_name",
                (self.config.database,),
            )
            indexes = self._query(
                conn,
                "SELECT index_name, table_name, seq_in_index, column_name, index_type "
                "FROM information_schema.statistics WHERE table_schema = %s "
                "AND table_name IN ('npc_player', 'npc_turn') "
                "ORDER BY table_name, index_name, seq_in_index",
                (self.config.database,),
            )
        grouped: dict[str, dict[str, Any]] = {}
        for row in indexes:
            entry = grouped.setdefault(
                row["index_name"],
                {"index_name": row["index_name"], "table_name": row["table_name"],
                 "index_type": row["index_type"], "columns": []},
            )
            entry["columns"].append(row["column_name"])
        return {
            "database": self.config.database,
            "tables": [dict(row) for row in tables],
            "indexes": list(grouped.values()),
            "fts_parser": self._fts_parser,
        }

