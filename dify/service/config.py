"""Tiny environment-file loader shared by the deploy and validation scripts.

The service itself reads plain environment variables (see
``dify/service/db.py``); this helper only exists so that the operator can
keep secrets in a single ``dify/.env`` file instead of exporting them by
hand.  Values already present in the environment always win.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env_file(path: str | os.PathLike[str] | None = None, *, override: bool = False) -> dict[str, str]:
    """Load ``KEY=VALUE`` pairs from a dotenv-style file into ``os.environ``.

    Returns the values that were actually applied.  Missing files are not an
    error - the caller may rely purely on the ambient environment.
    """
    env_path = Path(path) if path is not None else DEFAULT_ENV_FILE
    if not env_path.is_file():
        return {}

    applied: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied
