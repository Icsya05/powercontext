"""Capture real seekdb row-level evidence for the NPC memory.

Writes a realistic turn through the memory service HTTP API (the exact path the
Dify workflow uses), then reads the raw rows back out of seekdb and prints them
as the evidence that will be quoted in the submission.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dify.service.config import load_env_file  # noqa: E402
from dify.service.db import SeekDbStore, StoreConfig  # noqa: E402

BASE = "http://127.0.0.1:8077"
PLAYER = "player_042"

TURNS = [
    {
        "player_id": PLAYER,
        "player_input": "老板，我上次落在收银台的那把黑伞还在吗？",
        "npc_reply": "在的。收银台左边第二个伞桶，黑伞，柄上系着一截褪色的红绳。我给你收着呢。",
        "choices": ["谢谢老板，麻烦你了", "再买一瓶热牛奶", "顺便来包烟"],
        "chapter": "雨夜初遇",
        "bond_delta": 3,
        "favourite": "热牛奶",
        "running_joke": "关东煮的萝卜今天又被你点名了",
        "display_name": "夜班常客",
        "action": "save",
    },
    {
        "player_id": PLAYER,
        "player_input": "我今天加班到十一点，伞还在就踏实了。",
        "npc_reply": "十一点啊，那关东煮只剩萝卜和海带了。萝卜给你留着，算你今晚的加班费。",
        "choices": ["来份萝卜", "其实我想喝热可可", "明天见"],
        "chapter": "雨夜初遇",
        "bond_delta": 2,
        "favourite": "热牛奶",
        "running_joke": "关东煮的萝卜今天又被你点名了",
        "display_name": "夜班常客",
        "action": "save",
    },
]


def post(path: str, payload: dict) -> dict:
    import urllib.request

    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    load_env_file(REPO_ROOT / "dify" / ".env")

    # Start from a clean slate so the evidence is reproducible.
    post("/api/turn", {"player_id": PLAYER, "action": "reset"})

    print("=" * 72)
    print("STEP 1 - write two turns through the memory service HTTP API")
    print("=" * 72)
    for turn in TURNS:
        result = post("/api/turn", turn)
        saved = result.get("state", {})
        print(f"  saved turn_no={saved.get('turn_no')} "
              f"visit_count={saved.get('visit_count')} "
              f"bond_score={saved.get('bond_score')} "
              f"ok={result.get('ok')}")

    print()
    print("=" * 72)
    print("STEP 2 - read the same data back through a NEW session (no in-process state)")
    print("=" * 72)
    import urllib.request

    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/api/state?player_id={PLAYER}", method="GET"), timeout=20
    ) as resp:
        state = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(state, ensure_ascii=False, indent=2)[:1400])

    print()
    print("=" * 72)
    print("STEP 3 - the rows that actually live in seekdb")
    print("=" * 72)
    store = SeekDbStore(StoreConfig())
    import pymysql

    conn = pymysql.connect(
        host=store.config.host,
        port=store.config.port,
        user=store.config.full_user,
        password=store.config.password,
        database=store.config.database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, player_id, turn_no, chapter, player_input, npc_reply, "
                "choices, created_at FROM npc_turn ORDER BY turn_no"
            )
            rows = cur.fetchall()
            for row in rows:
                print(f"  npc_turn row id={row[0]} player={row[1]} turn_no={row[2]} "
                      f"chapter={row[3]}")
                print(f"      player_input: {row[4]}")
                print(f"      npc_reply   : {row[5]}")
                print(f"      choices     : {row[6]}")
                print(f"      created_at  : {row[7]}")
            cur.execute(
                "SELECT player_id, display_name, visit_count, bond_score, chapter, "
                "favourite, running_joke, last_input FROM npc_player"
            )
            for row in cur.fetchall():
                print(f"  npc_player row player={row[0]} name={row[1]} "
                      f"visit_count={row[2]} bond_score={row[3]} chapter={row[4]}")
                print(f"      favourite={row[5]!r} running_joke={row[6]!r}")
                print(f"      last_input={row[7]!r}")
    finally:
        conn.close()

    print()
    print("=" * 72)
    print("STEP 4 - full-text recall inside seekdb (MATCH ... AGAINST)")
    print("=" * 72)
    recalled, mode = store.recall_memories(PLAYER, "伞", limit=5)
    print(f"  recall_memories(player, '伞') -> mode={mode}, {len(recalled)} row(s)")
    for item in recalled:
        print(f"      turn_no={item['turn_no']} player_input={item['player_input']}")

    print()
    print("=" * 72)
    print("STEP 5 - player isolation check against the same database")
    print("=" * 72)
    other = "player_999"
    post("/api/turn", {"player_id": other, "action": "reset"})
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/api/state?player_id={other}", method="GET"), timeout=20
    ) as resp:
        other_state = json.loads(resp.read().decode("utf-8"))
    print(f"  {PLAYER} visit_count = {(state.get('state') or {}).get('visit_count')}")
    print(f"  {other} visit_count = {(other_state.get('state') or {}).get('visit_count')} "
          f"(must be None - a brand new player has no history)")
    print(f"  {other} found = {other_state.get('found')} (must be False)")
    print(f"  players known in seekdb = {store.list_players()}")

    post("/api/turn", {"player_id": PLAYER, "action": "reset"})
    post("/api/turn", {"player_id": other, "action": "reset"})
    print("\n(evidence rows were cleaned up afterwards; re-run this script to reproduce)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
