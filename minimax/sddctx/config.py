"""Configuration and path resolution for the SDD context module.

Every credential comes from the git-ignored ``minimax/.env``.  Values that are
already present in the process environment win, so the module can be driven
from CI without touching that file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: ``minimax/sddctx/config.py`` -> ``minimax/sddctx`` -> ``minimax`` -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
MINIMAX_DIR = REPO_ROOT / "minimax"
SPECS_DIR = MINIMAX_DIR / "specs"
TASKS_DIR = MINIMAX_DIR / "tasks"
SAMPLE_PROJECT_DIR = MINIMAX_DIR / "sample_project" / "jmespath"
BEFORE_SNAPSHOT_DIR = MINIMAX_DIR / "sample_project" / "before"
EVIDENCE_DIR = MINIMAX_DIR / "evidence"
RAW_EVIDENCE_DIR = EVIDENCE_DIR / "raw"
DEFAULT_ENV_FILE = MINIMAX_DIR / ".env"


class ConfigError(RuntimeError):
    """Raised when the module is not configured well enough to run."""


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Load ``KEY=VALUE`` pairs from a dotenv-style file into ``os.environ``.

    Values that already exist in the environment are never overwritten.
    """
    env_path = path or DEFAULT_ENV_FILE
    if not env_path.is_file():
        return {}
    applied: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in os.environ:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied


@dataclass(frozen=True)
class SeekDBConfig:
    host: str
    port: int
    user: str
    password: str
    tenant: str
    database: str
    connect_timeout: int
    read_timeout: int

    @property
    def full_user(self) -> str:
        """seekdb authenticates as ``user@tenant``."""
        return f"{self.user}@{self.tenant}"


@dataclass(frozen=True)
class MiniMaxConfig:
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class PowerContextConfig:
    base_url: str
    scope: str


@dataclass(frozen=True)
class Config:
    seekdb: SeekDBConfig
    minimax: MiniMaxConfig
    powercontext: PowerContextConfig
    sample_project: Path


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not configured. Put it in {DEFAULT_ENV_FILE} (git-ignored) "
            "or export it before running the module."
        )
    return value


def load_config(env_file: Path | None = None) -> Config:
    """Build the effective configuration from the environment and ``minimax/.env``."""
    load_env_file(env_file)

    seekdb = SeekDBConfig(
        host=os.environ.get("SEEKDB_HOST", "127.0.0.1"),
        port=int(os.environ.get("SEEKDB_PORT", "2881")),
        user=os.environ.get("SEEKDB_USER", "root"),
        password=os.environ.get("SEEKDB_PASSWORD", ""),
        tenant=os.environ.get("SEEKDB_TENANT", "sys"),
        database=os.environ.get("SEEKDB_DATABASE", "sdd_context"),
        connect_timeout=int(os.environ.get("SEEKDB_CONNECT_TIMEOUT", "10")),
        read_timeout=int(os.environ.get("SEEKDB_READ_TIMEOUT", "30")),
    )
    minimax = MiniMaxConfig(
        base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/"),
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M3"),
        api_key=_require("MINIMAX_API_KEY"),
    )
    powercontext = PowerContextConfig(
        base_url=os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/"),
        scope=os.environ.get("POWERCONTEXT_SCOPE", "sdd-demo"),
    )
    sample_project = Path(
        os.environ.get("SAMPLE_PROJECT_PATH", str(SAMPLE_PROJECT_DIR))
    )
    if not sample_project.is_absolute():
        sample_project = (REPO_ROOT / sample_project).resolve()

    return Config(
        seekdb=seekdb,
        minimax=minimax,
        powercontext=powercontext,
        sample_project=sample_project,
    )
