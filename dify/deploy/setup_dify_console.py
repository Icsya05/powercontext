"""Bootstrap the Dify console admin account for a fresh Dify 1.17.1 install.

Dify's first-run wizard is normally a browser form.  This performs exactly the
same HTTP call the console makes (``POST /console/api/setup``) so that the
validation run can be reproduced from the command line.

The generated credentials are written to ``dify/.env`` (git-ignored) as
``DIFY_EMAIL`` / ``DIFY_PASSWORD`` and are never printed in full.

Usage (from the repository root):

    python dify/deploy/setup_dify_console.py [--dify-url http://localhost]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / "dify" / ".env"

DEFAULT_EMAIL = "admin@midnight-store.local"


def _request(method: str, url: str, payload: dict | None = None, timeout: float = 60.0):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"cannot reach {url}: {exc.reason}")
        raise SystemExit(3) from exc


def generate_password() -> str:
    """A password that satisfies Dify's rule: >= 8 chars, letters and digits."""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "Dify" + "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isalpha() for c in candidate) and any(c.isdigit() for c in candidate):
            return candidate


def write_env(email: str, password: str) -> None:
    """Persist the credentials into the git-ignored dify/.env file."""
    lines: list[str] = []
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    kept: list[str] = []
    for line in lines:
        if line.startswith("DIFY_EMAIL=") or line.startswith("DIFY_PASSWORD="):
            continue
        kept.append(line)

    kept.append(f"DIFY_EMAIL={email}")
    kept.append(f"DIFY_PASSWORD={password}")
    kept.append("")

    ENV_PATH.write_text("\n".join(kept), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the Dify console admin account.")
    parser.add_argument("--dify-url", default=os.getenv("DIFY_URL", "http://localhost"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--name", default="MidnightStore Admin")
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", ""))
    args = parser.parse_args()

    base = args.dify_url.rstrip("/")

    status, body = _request("GET", f"{base}/console/api/setup")
    print(f"GET /console/api/setup -> {status} {body}")
    if status != 200:
        return 2

    if json.loads(body).get("step") == "finished":
        print("Dify is already set up. Re-using the credentials from dify/.env.")
        return 0

    password = args.password or generate_password()
    payload = {"email": args.email, "name": args.name, "password": password, "language": "zh-Hans"}
    status, body = _request("POST", f"{base}/console/api/setup", payload)
    print(f"POST /console/api/setup -> {status} {body}")
    if status not in (200, 201):
        print("setup failed", file=sys.stderr)
        return 2

    write_env(args.email, password)
    print(f"admin account created: {args.email}")
    print(f"credentials written to {ENV_PATH} (git-ignored, never committed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
