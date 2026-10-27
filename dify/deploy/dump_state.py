"""Print the real rows that seekdb holds for the NPC memory.

Used as evidence in the validation report: it talks to seekdb directly with
the MySQL protocol, so what it prints is what is actually stored, not what the
service claims.

Usage (from the repository root):

    python dify/deploy/dump_state.py --env dify/.env
    python dify/deploy/dump_state.py --env dify/.env --player-id demo_001 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dify.service.config import load_env_file  # noqa: E402
from dify.service.db import DatabaseUnavailable, SeekDbStore, StoreConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump the NPC memory tables from seekdb.")
    parser.add_argument("--env", default=None, help="path to a .env file (default: dify/.env)")
    parser.add_argument("--player-id", default=None, help="only show this player")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    load_env_file(args.env)
    store = SeekDbStore(StoreConfig())

    try:
        schema = store.describe_schema()
        players = store.list_players()
        payload = {
            "schema": schema,
            "players": players,
            "player_states": {},
            "turns": {},
        }
        targets = [args.player_id] if args.player_id else players
        for player_id in targets:
            if not player_id:
                continue
            payload["player_states"][player_id] = store.get_player(player_id)
            payload["turns"][player_id] = store.recent_turns(player_id, limit=args.limit)
    except DatabaseUnavailable as exc:
        print(f"FAILED: {exc}")
        return 2

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"database : {schema['database']}")
    print(f"tables   : {', '.join(t['table_name'] for t in schema['tables'])}")
    print(f"indexes  : {', '.join(i['index_name'] for i in schema['indexes'])}")
    print(f"fts      : {schema['fts_parser']}")
    print(f"players  : {players or '(none)'}")
    for player_id, state in payload["player_states"].items():
        if not state:
            continue
        print("")
        print(f"--- npc_player [{player_id}] ---")
        for key in (
            "display_name", "visit_count", "bond_score", "chapter",
            "favourite", "running_joke", "last_input", "last_reply",
            "first_seen_at", "last_seen_at", "updated_at",
        ):
            print(f"  {key:<14}: {state.get(key)}")
        turns = payload["turns"].get(player_id) or []
        print(f"--- npc_turn [{player_id}] ({len(turns)} rows) ---")
        for turn in sorted(turns, key=lambda t: t.get("turn_no") or 0):
            print(f"  #{turn.get('turn_no')} [{turn.get('chapter')}]")
            print(f"     玩家: {turn.get('player_input')}")
            print(f"     阿澈: {turn.get('npc_reply')}")
            print(f"     选项: {turn.get('choices')}")
            print(f"     时间: {turn.get('created_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
