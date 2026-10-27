"""HTTP bridge between the Dify workflow and the seekdb memory store.

Dify owns the orchestration (input handling, HTTP calls, LLM generation,
branching, output).  This service owns persistence: it reads and writes the
NPC's long-term memory in seekdb.

Design rules that the workflow relies on:

* Every response carries an ``ok`` flag.  When seekdb is unreachable the
  service answers ``200`` with ``ok=false`` and a human readable ``message``,
  so Dify can show the player a clear error instead of pretending that the
  memory was saved.
* ``GET  /api/state`` never creates a player; a missing player simply means
  "first visit".
* ``DELETE /api/state`` wipes exactly one player and leaves every other
  player's rows untouched.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .db import DatabaseUnavailable, InvalidPlayerId, SeekDbStore, validate_player_id

LOGGER = logging.getLogger("dify.npc_memory")

app = FastAPI(
    title="Midnight Convenience Store - NPC memory service",
    version="1.0.0",
    description="seekdb-backed long-term memory for the Dify NPC workflow.",
)

STORE = SeekDbStore()


class TurnRequest(BaseModel):
    """One completed NPC turn, produced by the Dify LLM node."""

    player_id: str = Field(min_length=1, max_length=64)
    player_input: str = Field(default="", max_length=500)
    npc_reply: str = Field(default="", max_length=2000)
    choices: list[str] = Field(default_factory=list)
    chapter: str = Field(default="雨夜初遇", max_length=64)
    bond_delta: int = 0
    favourite: str = Field(default="", max_length=128)
    running_joke: str = Field(default="", max_length=256)
    display_name: str = Field(default="", max_length=64)
    action: str = Field(default="continue", description="continue | reset")


class StateRequest(BaseModel):
    """Read one player's stored state (POST variant used by the Dify node)."""

    player_id: str = Field(min_length=1, max_length=64)
    query: str = Field(default="", max_length=500)


def _error(code: str, message: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "code": code, "message": message})


@app.get("/api/health")
def health() -> JSONResponse:
    """Report whether the service and seekdb are both reachable."""
    db_ok = STORE.ping()
    return JSONResponse(
        status_code=200,
        content={
            "ok": db_ok,
            "service": "up",
            "db": {
                "ok": db_ok,
                "host": STORE.config.host,
                "port": STORE.config.port,
                "user": STORE.config.full_user,
                "database": STORE.config.database,
                "fts_parser": STORE._fts_parser,
            },
            "message": "" if db_ok else "seekdb 不可用：记忆读写全部失败",
        },
    )


@app.get("/api/state")
def get_state(
    player_id: str = Query(..., description="玩家标识（会员卡号）"),
    query: str = Query("", description="用于全文检索召回的关键词"),
) -> JSONResponse:
    """Read the player's stored state and recall relevant past turns."""
    return _read_state(player_id, query)


@app.post("/api/state")
def post_state(payload: StateRequest) -> JSONResponse:
    """POST variant of :func:`get_state` (used by the Dify HTTP Request node).

    The body form keeps non-ASCII input out of the query string, so Chinese
    player input survives the trip through Dify unchanged.
    """
    return _read_state(payload.player_id, payload.query)


def _read_state(player_id: str, query: str = "") -> JSONResponse:
    """Shared implementation behind GET and POST /api/state."""
    try:
        pid = validate_player_id(player_id)
    except InvalidPlayerId as exc:
        return _error("INVALID_PLAYER_ID", f"玩家标识无效：{exc}")

    try:
        state = STORE.get_player(pid)
        memories, recall_mode = STORE.recall_memories(pid, query)
    except DatabaseUnavailable as exc:
        LOGGER.error("seekdb unavailable while reading state: %s", exc)
        return _error("DB_UNAVAILABLE", f"记忆库暂时不可用，本次没有读取到任何记忆：{exc}")

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "player_id": pid,
            "found": state is not None,
            "is_returning": state is not None,
            "state": state,
            "memories": memories,
            "recall_mode": recall_mode,
            "message": "",
        },
    )


@app.post("/api/turn")
def save_turn(payload: TurnRequest) -> JSONResponse:
    """Persist one NPC turn and update the player's aggregate state.

    ``action="reset"`` turns this into a reset: the player's state and their
    whole dialogue history are deleted instead of a new turn being written.
    """
    try:
        pid = validate_player_id(payload.player_id)
    except InvalidPlayerId as exc:
        return _error("INVALID_PLAYER_ID", f"玩家标识无效：{exc}")

    if payload.action.strip().lower() == "reset":
        try:
            result = STORE.reset_player(pid)
        except DatabaseUnavailable as exc:
            LOGGER.error("seekdb unavailable while resetting player: %s", exc)
            return _error("DB_UNAVAILABLE", f"记忆库暂时不可用，重置没有完成：{exc}")
        return JSONResponse(
            status_code=200,
            content={"ok": True, "player_id": pid, "reset": True, **result, "message": ""},
        )

    try:
        state = STORE.save_turn(
            pid,
            player_input=payload.player_input,
            npc_reply=payload.npc_reply,
            choices=payload.choices,
            chapter=payload.chapter,
            bond_delta=payload.bond_delta,
            favourite=payload.favourite,
            running_joke=payload.running_joke,
            display_name=payload.display_name,
        )
    except DatabaseUnavailable as exc:
        LOGGER.error("seekdb unavailable while saving turn: %s", exc)
        return _error(
            "DB_UNAVAILABLE",
            f"记忆库暂时不可用，本轮对话没有被保存：{exc}",
        )

    return JSONResponse(
        status_code=200,
        content={"ok": True, "player_id": pid, "state": state, "message": ""},
    )


@app.delete("/api/state")
def reset_state(player_id: str = Query(..., description="玩家标识（会员卡号）")) -> JSONResponse:
    """Reset one player: delete their state and their dialogue history."""
    try:
        pid = validate_player_id(player_id)
    except InvalidPlayerId as exc:
        return _error("INVALID_PLAYER_ID", f"玩家标识无效：{exc}")

    try:
        result = STORE.reset_player(pid)
    except DatabaseUnavailable as exc:
        LOGGER.error("seekdb unavailable while resetting player: %s", exc)
        return _error("DB_UNAVAILABLE", f"记忆库暂时不可用，重置没有完成：{exc}")

    return JSONResponse(
        status_code=200,
        content={"ok": True, "reset": True, **result, "message": ""},
    )


@app.get("/api/admin/players")
def admin_players() -> JSONResponse:
    """List every known player id (evidence helper for the validation run)."""
    try:
        players = STORE.list_players()
    except DatabaseUnavailable as exc:
        return _error("DB_UNAVAILABLE", f"记忆库暂时不可用：{exc}")
    return JSONResponse(status_code=200, content={"ok": True, "players": players})


@app.get("/api/admin/turns")
def admin_turns(
    player_id: str = Query(..., description="玩家标识（会员卡号）"),
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    """Return the raw dialogue rows of one player (evidence helper)."""
    try:
        pid = validate_player_id(player_id)
    except InvalidPlayerId as exc:
        return _error("INVALID_PLAYER_ID", f"玩家标识无效：{exc}")
    try:
        turns = STORE.recent_turns(pid, limit=limit)
    except DatabaseUnavailable as exc:
        return _error("DB_UNAVAILABLE", f"记忆库暂时不可用：{exc}")
    turns.reverse()
    return JSONResponse(status_code=200, content={"ok": True, "player_id": pid, "turns": turns})


@app.get("/api/admin/schema")
def admin_schema() -> JSONResponse:
    """Describe the seekdb schema actually in use (evidence helper)."""
    try:
        schema = STORE.describe_schema()
    except DatabaseUnavailable as exc:
        return _error("DB_UNAVAILABLE", f"记忆库暂时不可用：{exc}")
    return JSONResponse(status_code=200, content={"ok": True, "schema": schema})


@app.post("/api/admin/init")
def admin_init() -> JSONResponse:
    """Create the database, the tables and the full-text index."""
    try:
        STORE.ensure_database()
        info = STORE.ensure_schema()
    except DatabaseUnavailable as exc:
        return _error("DB_UNAVAILABLE", f"初始化失败：{exc}")
    return JSONResponse(status_code=200, content={"ok": True, **info, "message": ""})


@app.exception_handler(404)
def _not_found(_request: Any, _exc: Any) -> JSONResponse:
    return _error("NOT_FOUND", "接口不存在", status_code=404)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    import uvicorn

    uvicorn.run(
        "dify.service.app:app",
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVICE_PORT", "8077")),
        reload=False,
    )
