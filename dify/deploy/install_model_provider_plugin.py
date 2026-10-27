"""Install the OpenAI-API-compatible model provider plugin into Dify.

Installing the plugin needs no credentials; only configuring the provider with
an API key does, and that is left to the operator.

Usage (from the repository root):

    python dify/deploy/install_model_provider_plugin.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dify.service.config import load_env_file  # noqa: E402
from dify.validation.workflow_checks import Console  # noqa: E402

MARKETPLACE_API = "https://marketplace.dify.ai/api/v1"
PLUGIN_ID = "langgenius/openai_api_compatible"


def marketplace_latest_identifier(query: str = "openai_api_compatible") -> str:
    """Ask the marketplace for the current package identifier of the plugin."""
    import httpx

    response = httpx.post(
        f"{MARKETPLACE_API}/plugins/search/advanced",
        json={"page": 1, "page_size": 20, "query": query},
        timeout=60.0,
    )
    response.raise_for_status()
    plugins = (response.json().get("data") or {}).get("plugins") or []
    for plugin in plugins:
        if plugin.get("plugin_id") == PLUGIN_ID:
            return str(plugin["latest_package_identifier"])
    raise SystemExit(f"{PLUGIN_ID} not found in the marketplace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the OpenAI-compatible model provider.")
    parser.add_argument("--dify-url", default=os.getenv("DIFY_URL", "http://localhost"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", ""))
    args = parser.parse_args()

    load_env_file(REPO_ROOT / "dify" / ".env")
    email = args.email or os.getenv("DIFY_EMAIL", "")
    password = args.password or os.getenv("DIFY_PASSWORD", "")
    if not email or not password:
        print("DIFY_EMAIL / DIFY_PASSWORD are required (Dify console account).")
        return 2

    console = Console(args.dify_url)
    console.login(email, password)

    status, body = console.json_request(
        "GET", "/console/api/workspaces/current/plugin/list?page=1&page_size=100"
    )
    installed = [p.get("plugin_id") for p in (body.get("plugins") or [])]
    if PLUGIN_ID in installed:
        print(f"{PLUGIN_ID} is already installed")
        return 0

    identifier = marketplace_latest_identifier()
    print(f"installing {identifier}")

    status, body = console.json_request(
        "POST",
        "/console/api/workspaces/current/plugin/install/marketplace",
        json_body={"plugin_unique_identifiers": [identifier]},
    )
    print(f"install request -> {status} {json.dumps(body, ensure_ascii=False)[:300]}")
    if status not in (200, 201, 202):
        return 2

    # The plugin daemon installs asynchronously; poll the plugin list.
    for _ in range(30):
        time.sleep(5)
        status, body = console.json_request(
            "GET", "/console/api/workspaces/current/plugin/list?page=1&page_size=100"
        )
        for plugin in body.get("plugins") or []:
            if plugin.get("plugin_id") == PLUGIN_ID:
                declaration = plugin.get("declaration") or {}
                print(f"installed: {PLUGIN_ID} version={declaration.get('version')} "
                      f"category={declaration.get('category')}")
                return 0
    print("the plugin did not show up within the timeout; check the plugin_daemon logs")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
