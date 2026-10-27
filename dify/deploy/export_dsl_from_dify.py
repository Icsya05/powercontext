"""Save the DSL that Dify actually exports, as a committed evidence artefact.

This is the file a reviewer would get back from "导出 DSL" in the Dify console.
It is stored next to the validation reports so the round trip can be inspected
without re-running Dify.

Usage (from the repository root):

    python dify/deploy/export_dsl_from_dify.py --dify-url http://localhost
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dify.service.config import load_env_file  # noqa: E402
from dify.validation.workflow_checks import Console  # noqa: E402

OUT_DIR = REPO_ROOT / "dify" / "validation"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the DSL from the live Dify console.")
    parser.add_argument("--dify-url", default=os.getenv("DIFY_URL", "http://localhost"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", ""))
    parser.add_argument("--app-id", default=os.getenv("DIFY_APP_ID", ""))
    parser.add_argument("--out", default=str(OUT_DIR / "dsl_exported.yml"))
    args = parser.parse_args()

    load_env_file(REPO_ROOT / "dify" / ".env")
    email = args.email or os.getenv("DIFY_EMAIL", "")
    password = args.password or os.getenv("DIFY_PASSWORD", "")
    if not email or not password:
        print("DIFY_EMAIL / DIFY_PASSWORD are required (Dify console account).")
        return 2

    console = Console(args.dify_url)
    console.login(email, password)

    app_id = args.app_id
    if not app_id:
        status, body = console.json_request("GET", "/console/api/apps?page=1&limit=50")
        apps = body.get("data") or []
        if not apps:
            print("no application found in the workspace")
            return 2
        app_id = str(apps[0]["id"])
        print(f"using app {app_id} ({apps[0].get('name')})")

    text = console.export_dsl(app_id)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"exported {len(text.encode('utf-8'))} bytes to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
