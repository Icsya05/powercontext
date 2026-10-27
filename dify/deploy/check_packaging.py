"""Static check of the deployment packaging for the NPC memory service.

Catches the mistakes that only show up at `docker compose up` time, before
Docker is even installed:

* ``docker-compose.yml`` must parse and declare the two expected services;
* every ``${VAR}`` referenced by the compose file must have a matching key
  in ``dify/.env.example`` (and the example must not contain real secrets);
* the Dockerfile's COPY sources must exist in the repository;
* the memory service must be reachable from a Dify container, so the compose
  file has to publish the port the DSL points at.

Usage (from the repository root):

    python dify/deploy/check_packaging.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "dify" / "deploy" / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / "dify" / ".env.example"
DOCKERFILE = REPO_ROOT / "dify" / "service" / "Dockerfile"
WORKFLOW = REPO_ROOT / "dify" / "workflow.yml"

#: The port the Dify HTTP Request nodes point at.
EXPECTED_SERVICE_PORT = 8077


def main() -> int:
    parser = argparse.ArgumentParser(description="Static check of the deployment packaging.")
    parser.add_argument("--compose", default=str(COMPOSE))
    parser.add_argument("--env-example", default=str(ENV_EXAMPLE))
    parser.add_argument("--dockerfile", default=str(DOCKERFILE))
    parser.add_argument("--workflow", default=str(WORKFLOW))
    args = parser.parse_args()

    import yaml

    problems: list[str] = []
    notes: list[str] = []

    compose_path = Path(args.compose)
    env_path = Path(args.env_example)
    dockerfile_path = Path(args.dockerfile)

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services") or {}
    notes.append(f"compose services: {', '.join(sorted(services))}")

    for required in ("seekdb", "memory-service"):
        if required not in services:
            problems.append(f"compose file is missing the {required!r} service")

    # --- env var wiring ------------------------------------------------
    env_text = env_path.read_text(encoding="utf-8")
    declared: dict[str, str] = {}
    for raw in env_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        declared[key.strip()] = value.strip()

    referenced = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", compose_path.read_text(encoding="utf-8")))
    missing = sorted(referenced - set(declared))
    if missing:
        problems.append(f"compose references variables absent from .env.example: {missing}")
    unused = sorted(set(declared) - referenced)
    if unused:
        notes.append(f"declared in .env.example but not referenced by compose: {unused}")

    for key, value in declared.items():
        if key.endswith("_PASSWORD") or key.endswith("_KEY") or "TOKEN" in key:
            if value and not value.upper().startswith("YOUR_") and "YOUR_" not in value:
                problems.append(f".env.example must only carry placeholders, but {key} looks real")

    # --- Dockerfile ----------------------------------------------------
    docker_text = dockerfile_path.read_text(encoding="utf-8")
    for match in re.finditer(r"^COPY\s+(\S+)\s+(\S+)", docker_text, flags=re.MULTILINE):
        source = match.group(1)
        if source.startswith("--"):
            continue
        if not (REPO_ROOT / source).exists():
            problems.append(f"Dockerfile COPY source does not exist: {source}")
    if "dify/service/requirements.txt" not in docker_text:
        problems.append("Dockerfile does not install dify/service/requirements.txt")

    # --- the port the workflow actually calls --------------------------
    workflow_text = Path(args.workflow).read_text(encoding="utf-8")
    urls = sorted(set(re.findall(r"url:\s*(\S+)", workflow_text)))
    notes.append(f"workflow service URLs: {urls}")
    for url in urls:
        if f":{EXPECTED_SERVICE_PORT}" not in url:
            problems.append(
                f"workflow URL {url} does not point at the memory service port {EXPECTED_SERVICE_PORT}"
            )

    publish = services.get("memory-service", {}).get("ports") or []
    if not any(str(EXPECTED_SERVICE_PORT) in str(item) for item in publish):
        problems.append(f"memory-service does not publish port {EXPECTED_SERVICE_PORT}")

    # --- notes ---------------------------------------------------------
    for note in notes:
        print(f"  - {note}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    print("\npackaging OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
