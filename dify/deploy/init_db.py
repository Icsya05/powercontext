"""Create the seekdb database, tables and full-text index for the NPC memory.

Usage (from the repository root):

    python dify/deploy/init_db.py [--env dify/.env]

The script is idempotent: it can be re-run at any time.
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
    parser = argparse.ArgumentParser(description="Initialise the seekdb memory schema.")
    parser.add_argument("--env", default=None, help="path to a .env file (default: dify/.env)")
    args = parser.parse_args()

    applied = load_env_file(args.env)
    if applied:
        print(f"loaded {len(applied)} variable(s) from {args.env or 'dify/.env'}")

    store = SeekDbStore(StoreConfig())
    print(f"target: {store.config.host}:{store.config.port} "
          f"user={store.config.full_user} db={store.config.database}")

    try:
        store.ensure_database()
        print("database: ready")
        info = store.ensure_schema()
        print(f"tables: ready (full-text parser: {info['fts_parser']})")
        players = store.list_players()
        print(f"players currently known: {len(players)}")
    except DatabaseUnavailable as exc:
        print(f"FAILED: {exc}")
        return 2

    print(json.dumps({"ok": True, **info}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
