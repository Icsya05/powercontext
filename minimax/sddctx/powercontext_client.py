"""PowerContext client - the task-state store of the SDD context module.

The module uses three PowerContext facilities:

* **Scope** - one isolated boundary per development task.
* **Work Contract / Task Outcome** - the inspectable delegation baseline and
  the per-step results (PowerContext records them as exact Source evidence).
* **Atomic Memory** - the task state itself, written after every step and
  read back with ``POST /v1/memory/search`` when the module starts again.

Everything goes through the documented HTTP API of PowerContext 1.4.1.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import PowerContextConfig

WORK_CONTRACT_SCHEMA = "powercontext.work-contract.v1"
TASK_OUTCOME_SCHEMA = "powercontext.task-outcome.v1"
STATE_KIND = "sdd.task.state"


class PowerContextError(RuntimeError):
    """Raised when PowerContext rejects a request or cannot be reached."""


@dataclass
class ScopeInfo:
    scope_id: str
    title: str
    summary: str


class PowerContextClient:
    """Thin HTTP client for the PowerContext server."""

    def __init__(self, config: PowerContextConfig, recorder=None) -> None:
        self.config = config
        self.recorder = recorder

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self.config.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else None
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if self.recorder is not None:
                self.recorder.record(
                    "powercontext.error",
                    method=method,
                    path=path,
                    status=exc.code,
                    detail=detail[:600],
                )
            raise PowerContextError(f"PowerContext {method} {path} -> HTTP {exc.code}: {detail[:600]}") from exc
        except Exception as exc:  # noqa: BLE001
            if self.recorder is not None:
                self.recorder.record("powercontext.error", method=method, path=path, detail=str(exc)[:400])
            raise PowerContextError(f"cannot reach PowerContext at {url}: {exc}") from exc

        if self.recorder is not None:
            self.recorder.record(
                "powercontext.call",
                method=method,
                path=path,
                status=status,
                request=_summarize(body),
                response=_summarize(payload),
            )
        return payload

    # ------------------------------------------------------------------
    # scopes
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.config.base_url}/health/ready", method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def ensure_scope(self, task_id: str, title: str, summary: str) -> ScopeInfo:
        """Return the scope for ``task_id``, creating it on first use.

        The idempotency key makes the call safe to repeat, so a restarted
        module finds the scope it created before.  PowerContext binds the key
        to the parameters of the first call, so a later call with different
        parameters answers 409; in that case the existing scope is looked up
        and reused.
        """
        try:
            payload = self._call(
                "POST",
                "/v1/scopes",
                {
                    "title": title,
                    "summary": summary,
                    "idempotency_key": f"sddctx:{task_id}",
                },
            )
        except PowerContextError as exc:
            if "scope_idempotency_conflict" not in str(exc):
                raise
            existing = self.find_scope(task_id)
            if existing is None:
                raise
            return existing
        if isinstance(payload, dict) and "scope_id" in payload:
            return ScopeInfo(
                scope_id=payload["scope_id"],
                title=payload.get("title", title),
                summary=payload.get("summary", summary),
            )
        # idempotent replay returns the existing scope in a list
        items = (payload or {}).get("items") or []
        for item in items:
            if item.get("title") == title:
                return ScopeInfo(
                    scope_id=item["scope_id"],
                    title=item.get("title", title),
                    summary=item.get("summary", summary),
                )
        raise PowerContextError(f"unexpected scope response: {payload!r}")

    def find_scope(self, task_id: str) -> ScopeInfo | None:
        """Look up the scope that belongs to ``task_id``."""
        payload = self._call("GET", "/v1/scopes?limit=100")
        items = (payload or {}).get("items") or []
        exact = [item for item in items if item.get("title") == f"sdd task {task_id}"]
        candidates = exact or [item for item in items if task_id in (item.get("title") or "")]
        if not candidates:
            return None
        item = candidates[0]
        return ScopeInfo(
            scope_id=item["scope_id"],
            title=item.get("title", ""),
            summary=item.get("summary", ""),
        )

    def list_scopes(self) -> list[dict[str, Any]]:
        payload = self._call("GET", "/v1/scopes?limit=50")
        return list((payload or {}).get("items") or [])

    # ------------------------------------------------------------------
    # work contract / outcome
    # ------------------------------------------------------------------
    def create_work_contract(self, scope_id: str, source_id: str, contract: dict[str, Any]) -> dict[str, Any]:
        body = {"scope_id": scope_id, "source_id": source_id, "contract": contract}
        return self._call("POST", "/v1/work/contracts/create", body) or {}

    def record_outcome(self, scope_id: str, source_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
        body = {"scope_id": scope_id, "source_id": source_id, "outcome": outcome}
        return self._call("POST", "/v1/work/outcomes/record", body) or {}

    # ------------------------------------------------------------------
    # task state (atomic memory)
    # ------------------------------------------------------------------
    def remember_state(self, scope_id: str, state: dict[str, Any], reason: str = "") -> dict[str, Any]:
        body = {
            "scope_id": scope_id,
            "kind": STATE_KIND,
            "text": json.dumps(state, ensure_ascii=False, sort_keys=True),
            "reason": reason or "sddctx task state",
        }
        return self._call("POST", "/v1/memory/remember", body) or {}

    def search_state(self, scope_id: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        body = {"scope_id": scope_id, "query": query, "limit": limit, "mode": "auto"}
        payload = self._call("POST", "/v1/memory/search", body) or {}
        hits = payload.get("hits") or []
        return [hit.get("memory") or {} for hit in hits]

    def load_state(self, scope_id: str, task_id: str) -> dict[str, Any] | None:
        """Read the newest stored task state for ``task_id``.

        The state is written as one JSON document per step.  The newest
        revision wins, so the module can resume from wherever it stopped.
        """
        records = self.search_state(scope_id, task_id)
        best: dict[str, Any] | None = None
        best_key = None
        for record in records:
            if record.get("kind") != STATE_KIND:
                continue
            text = record.get("text")
            if not text:
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            if payload.get("task_id") != task_id:
                continue
            artifact = record.get("artifact") or {}
            key = (artifact.get("revision", 0), record.get("state_version", 0))
            if best_key is None or key >= best_key:
                best = payload
                best_key = key
        return best


def _summarize(payload: Any, limit: int = 700) -> Any:
    """Shorten a payload so the evidence log stays readable."""
    if payload is None:
        return None
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) <= limit:
        return payload
    return text[:limit] + f"... <{len(text)} chars>"
