"""Start a local Dify instance that can reach the NPC memory service.

This wraps the official Dify docker-compose stack and takes care of the two
settings that otherwise make the workflow fail:

1. ``SSRF_PROXY_ALLOW_PRIVATE_DOMAINS`` - Dify's Squid proxy denies private
   destinations by default, so the HTTP Request nodes could not reach the
   memory service.  The allowed host is added automatically.
2. ``SECRET_KEY`` - Dify refuses to start with the placeholder from
   ``.env.example`` on recent versions.

Usage:

    python dify/deploy/start_dify.py --dify-src /path/to/dify
    python dify/deploy/start_dify.py --dify-src /path/to/dify --memory-host memory-service
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIFY_VERSION = "1.17.1"
DEFAULT_MEMORY_HOST = "host.docker.internal"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed with exit code {result.returncode}")
    return result


def patch_env(env_path: Path, memory_host: str) -> None:
    """Ensure SECRET_KEY and the SSRF allowlist are set in Dify's .env."""
    text = env_path.read_text(encoding="utf-8")

    if "SECRET_KEY=" in text and text.split("SECRET_KEY=", 1)[1].splitlines()[0].strip():
        print("SECRET_KEY: already set")
    else:
        alphabet = string.ascii_letters + string.digits
        secret = "".join(secrets.choice(alphabet) for _ in range(48))
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("SECRET_KEY="):
                lines[index] = f"SECRET_KEY={secret}"
                break
        else:
            lines.append(f"SECRET_KEY={secret}")
        text = "\n".join(lines) + "\n"
        print("SECRET_KEY: generated")

    lines = text.splitlines()
    hosts = [memory_host]
    for index, line in enumerate(lines):
        if line.startswith("SSRF_PROXY_ALLOW_PRIVATE_DOMAINS="):
            existing = line.split("=", 1)[1].strip()
            if existing:
                hosts = [h.strip() for h in existing.split(",") if h.strip()]
                if memory_host not in hosts:
                    hosts.append(memory_host)
            lines[index] = "SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=" + ",".join(hosts)
            break
    else:
        lines.append("SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=" + memory_host)
    text = "\n".join(lines) + "\n"
    env_path.write_text(text, encoding="utf-8")
    print(f"SSRF_PROXY_ALLOW_PRIVATE_DOMAINS: {','.join(hosts)}")


def wait_for(url: str, timeout: float = 300.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Dify for the NPC memory workflow.")
    parser.add_argument("--dify-src", required=True, help="path to a Dify checkout")
    parser.add_argument("--memory-host", default=DEFAULT_MEMORY_HOST, help="host the memory service is reachable at")
    parser.add_argument("--compose", default="docker-compose.yaml", help="compose file inside the docker/ directory")
    parser.add_argument("--down", action="store_true", help="stop the stack instead of starting it")
    args = parser.parse_args()

    src = Path(args.dify_src).resolve()
    docker_dir = src / "docker"
    if not docker_dir.is_dir():
        print(f"not a Dify checkout: {docker_dir} is missing")
        return 2

    compose_cmd = ["docker", "compose", "-f", args.compose]
    if args.down:
        run([*compose_cmd, "down"], cwd=docker_dir)
        return 0

    env_path = docker_dir / ".env"
    if not env_path.exists():
        template = docker_dir / ".env.example"
        if not template.exists():
            print(f"missing {template}; cannot create .env")
            return 2
        print(f"creating {env_path} from .env.example")
        env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    patch_env(env_path, args.memory_host)

    run([*compose_cmd, "up", "-d"], cwd=docker_dir)

    console = "http://localhost/install"
    print("\nwaiting for the Dify console ...")
    if wait_for(console, timeout=420):
        print(f"Dify console is up: {console}")
        print("Next: create the admin account, configure the model provider, then import dify/workflow.yml")
        return 0
    print(f"Dify did not answer on {console} within the timeout; check `docker compose logs`.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
