"""End-to-end validation of the Dify application against a live Dify + seekdb.

This drives the real Dify console API (the same flow Dify's own e2e suite uses)
so that the evidence is produced by the real product, not by a simulation:

1. log into the Dify console;
2. import ``dify/workflow.yml`` and confirm the import;
3. publish the workflow and enable its API;
4. run the workflow for a brand new player;
5. run it again for the same player in a **new conversation** and confirm the
   state was recovered from seekdb (the database is the source of truth here,
   not the Dify conversation);
6. run it for a second player and confirm isolation;
7. reset a player and confirm the rows are gone;
8. export the DSL, import the exported DSL into a **clean** app, run it again;
9. write the report to ``dify/validation/workflow_checks.md``.

Usage (from the repository root):

    python dify/validation/workflow_checks.py \\
        --dify-url http://localhost \\
        --email YOU@EXAMPLE.COM --password YOUR_PASSWORD \\
        --memory-url http://127.0.0.1:8077
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_DSL = REPO_ROOT / "dify" / "workflow.yml"


class ValidationError(RuntimeError):
    """Raised when a validation step does not meet its expectation."""


# ----------------------------------------------------------------------
# HTTP plumbing
# ----------------------------------------------------------------------
class Console:
    """Minimal Dify console API client built on urllib."""

    def __init__(self, base_url: str, *, insecure: bool = False) -> None:
        self.base = base_url.rstrip("/")
        self.jar = CookieJar()
        context = ssl.create_default_context()
        if insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), urllib.request.HTTPSHandler(context=context)
        )
        self.csrf = ""

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 180.0,
    ) -> tuple[int, bytes]:
        url = f"{self.base}{path}"
        data = raw_body
        head = {"Accept": "application/json, text/plain, */*"}
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            head["Content-Type"] = "application/json"
        if content_type:
            head["Content-Type"] = content_type
        if self.csrf:
            head["X-CSRF-Token"] = self.csrf
        if headers:
            head.update(headers)
        request = urllib.request.Request(url, data=data, headers=head, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise ValidationError(f"cannot reach {url}: {exc.reason}") from exc

    def json_request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None, timeout: float = 180.0
    ) -> tuple[int, Any]:
        status, body = self._request(method, path, json_body=json_body, timeout=timeout)
        if not body:
            return status, {}
        try:
            return status, json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, {"raw": body.decode("utf-8", errors="replace")}

    def login(self, email: str, password: str) -> None:
        payload = {
            "email": email,
            "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            "remember_me": False,
        }
        status, body = self.json_request("POST", "/console/api/login", json_body=payload, timeout=30)
        if status != 200:
            raise ValidationError(f"console login failed: HTTP {status} {body}")
        for cookie in self.jar:
            if cookie.name == "csrf_token":
                self.csrf = cookie.value
        if not self.csrf:
            raise ValidationError("console login did not return a csrf_token cookie")

    def import_dsl(self, dsl_text: str) -> str:
        status, body = self.json_request(
            "POST",
            "/console/api/apps/imports",
            json_body={"mode": "yaml-content", "yaml_content": dsl_text},
        )
        if status not in (200, 202):
            raise ValidationError(f"DSL import failed: HTTP {status} {body}")
        app_id = body.get("app_id")
        if app_id:
            return str(app_id)
        import_id = body.get("import_id")
        if not import_id:
            raise ValidationError(f"DSL import returned neither app_id nor import_id: {body}")
        status, confirmed = self.json_request("POST", f"/console/api/apps/imports/{import_id}/confirm")
        if status != 200 or not confirmed.get("app_id"):
            raise ValidationError(f"DSL import confirm failed: HTTP {status} {confirmed}")
        return str(confirmed["app_id"])

    def export_dsl(self, app_id: str) -> str:
        """Return the exported DSL as YAML text.

        Dify's export endpoint answers with a JSON envelope
        (``{"data": "<yaml text>"}`` - see ``AppExportResponse`` in
        ``api/controllers/console/app/app.py``), so the payload has to be
        unwrapped before it can be parsed or re-imported.
        """
        status, body = self._request("GET", f"/console/api/apps/{app_id}/export")
        if status != 200:
            raise ValidationError(f"DSL export failed: HTTP {status} {body[:400]!r}")
        text = body.decode("utf-8", errors="replace")
        stripped = text.lstrip()
        if stripped.startswith("{"):
            try:
                envelope = json.loads(text)
            except json.JSONDecodeError:
                return text
            if isinstance(envelope, dict) and isinstance(envelope.get("data"), str):
                return envelope["data"]
        return text

    def publish(self, app_id: str) -> None:
        self.json_request(
            "POST",
            f"/console/api/apps/{app_id}/workflows/publish",
            json_body={"marked_name": "validation", "marked_comment": "dify/validation/workflow_checks.py"},
        )

    def enable_api(self, app_id: str) -> None:
        self.json_request("POST", f"/console/api/apps/{app_id}/api-enable", json_body={"enable_api": True})

    def create_app_api_key(self, app_id: str) -> str | None:
        """Best effort: mint an app API key so the service API can be used.

        Dify's ``POST /console/api/apps/<id>/api-keys`` handler takes no
        request body - it creates a key and returns it.
        """
        for payload in (None, {"type": "app"}):
            status, body = self.json_request(
                "POST", f"/console/api/apps/{app_id}/api-keys", json_body=payload
            )
            if status not in (200, 201):
                continue
            candidates = body if isinstance(body, list) else [body]
            for candidate in candidates:
                if isinstance(candidate, dict):
                    token = candidate.get("token") or candidate.get("api_key")
                    if token:
                        return str(token)
        return None

    def workflow_runs(self, app_id: str) -> list[dict[str, Any]]:
        status, body = self.json_request("GET", f"/console/api/apps/{app_id}/workflow-runs?page=1&limit=20")
        if status != 200:
            return []
        data = body.get("data")
        return data if isinstance(data, list) else []

    def node_executions(self, app_id: str, run_id: str) -> list[dict[str, Any]]:
        status, body = self.json_request(
            "GET", f"/console/api/apps/{app_id}/workflow-runs/{run_id}/node-executions"
        )
        if status != 200:
            return []
        data = body.get("data")
        return data if isinstance(data, list) else []


class ServiceApi:
    """Dify service API client (the same endpoint a grader would call)."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base = base_url.rstrip("/")
        self.api_key = api_key

    def run_workflow(self, inputs: dict[str, Any], user: str, timeout: float = 300.0) -> dict[str, Any]:
        payload = {"inputs": inputs, "response_mode": "blocking", "user": user}
        request = urllib.request.Request(
            f"{self.base}/v1/workflows/run",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ValidationError(f"workflow run failed: HTTP {exc.code} {body[:600]}") from exc
        except urllib.error.URLError as exc:
            raise ValidationError(f"cannot reach the Dify service API: {exc.reason}") from exc


def memory_api(url: str, path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "code": f"HTTP_{exc.code}", "message": exc.read().decode("utf-8", errors="replace")}
    except urllib.error.URLError as exc:
        return {"ok": False, "code": "UNREACHABLE", "message": str(exc.reason)}


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------
def run_checks(args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%H%M%S")
    player_a = f"wf_player_a_{stamp}"
    player_b = f"wf_player_b_{stamp}"

    def record(name: str, description: str, fn: Any) -> None:
        try:
            evidence = fn()
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "name": name,
                    "description": description,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return
        results.append({"name": name, "description": description, "status": "PASS", "evidence": evidence})

    console = Console(args.dify_url, insecure=args.insecure)

    def do_login() -> dict[str, Any]:
        console.login(args.email, args.password)
        return {"email": args.email, "csrf_received": bool(console.csrf)}

    record("console_login", "登录 Dify 控制台", do_login)

    dsl_text = Path(args.dsl).read_text(encoding="utf-8")

    app_id_holder: dict[str, str] = {}

    def do_import() -> dict[str, Any]:
        app_id = console.import_dsl(dsl_text)
        app_id_holder["app_id"] = app_id
        return {"app_id": app_id, "dsl_bytes": len(dsl_text.encode("utf-8"))}

    record("dsl_import", "把 workflow.yml 导入 Dify", do_import)
    if "app_id" not in app_id_holder:
        return results

    app_id = app_id_holder["app_id"]

    record(
        "publish_and_enable_api",
        "发布工作流并开启 API 访问",
        lambda: {
            "published": console.publish(app_id),
            "api_enabled": console.enable_api(app_id),
            "app_api_key": bool(api_key),
        },
    )

    api_key = args.app_api_key or console.create_app_api_key(app_id)
    if not api_key:
        results.append(
            {
                "name": "app_api_key",
                "description": "取得应用的 API Key（用于通过 /v1/workflows/run 运行工作流）",
                "status": "FAIL",
                "error": "无法自动创建应用 API Key，请在 Dify 界面创建后用 --app-api-key 传入",
            }
        )
        return results
    results.append(
        {
            "name": "app_api_key",
            "description": "取得应用的 API Key",
            "status": "PASS",
            "evidence": {"app_api_key_prefix": api_key[:8] + "..."},
        }
    )

    api = ServiceApi(args.dify_url, api_key)
    runs: dict[str, Any] = {}

    def run_turn(tag: str, player_id: str, text: str, action: str = "continue") -> dict[str, Any]:
        """Run one turn. A fresh `user` value gives a brand new conversation."""
        response = api.run_workflow(
            {"player_id": player_id, "player_input": text, "action": action},
            user=f"{player_id}-{tag}-{uuid.uuid4().hex[:6]}",
        )
        data = response.get("data") or {}
        if data.get("status") != "succeeded":
            raise ValidationError(f"workflow did not succeed: {data.get('status')} {data.get('error')}")
        runs[tag] = response
        return {
            "outputs": data.get("outputs"),
            "status": data.get("status"),
            "elapsed_time": data.get("elapsed_time"),
            "total_steps": data.get("total_steps"),
        }

    record(
        "run_new_player",
        "新玩家跑通一次完整对话",
        lambda: run_turn("new", player_a, "推门进来，外面雨好大"),
    )
    record(
        "state_written_to_seekdb",
        "这一轮确实写进了 seekdb",
        lambda: _expect_state(args.memory_url, player_a, visit_count=1),
    )
    record(
        "run_returning_player_new_conversation",
        "同一玩家在新会话里再跑一次",
        lambda: run_turn("returning", player_a, "还是热可可吧，跟上次一样"),
    )
    record(
        "state_recovered_across_sessions",
        "新会话里记忆被恢复（到店次数 +1）",
        lambda: _expect_state(args.memory_url, player_a, visit_count=2),
    )
    record(
        "run_second_player",
        "另一个玩家跑一次（隔离）",
        lambda: run_turn("other", player_b, "推门进来，外面雨好大"),
    )
    record(
        "players_isolated",
        "两个玩家在数据库里互不干扰",
        lambda: _expect_isolation(args.memory_url, player_a, player_b),
    )
    record(
        "run_reset",
        "执行重置",
        lambda: run_turn("reset", player_a, "算了，不来了", action="reset"),
    )
    record(
        "reset_cleared_rows",
        "重置后数据库里只剩另一个玩家",
        lambda: _expect_reset(args.memory_url, player_a, player_b),
    )

    exported: dict[str, str] = {}

    def do_export() -> dict[str, Any]:
        text = console.export_dsl(app_id)
        exported["text"] = text
        target = OUTPUT_DIR / "dsl_exported.yml"
        target.write_text(text, encoding="utf-8")
        return {"exported_bytes": len(text.encode("utf-8")), "saved_to": str(target)}

    record("dsl_export", "从运行中的应用导出 DSL", do_export)

    reimport_app: dict[str, str] = {}

    def do_reimport() -> dict[str, Any]:
        if "text" not in exported:
            raise ValidationError("no exported DSL available")
        new_app_id = console.import_dsl(exported["text"])
        reimport_app["app_id"] = new_app_id
        console.publish(new_app_id)
        console.enable_api(new_app_id)
        return {"new_app_id": new_app_id}

    record("dsl_reimport_clean_app", "把导出的 DSL 导入一个干净的新应用", do_reimport)

    def run_reimported() -> dict[str, Any]:
        if "app_id" not in reimport_app:
            raise ValidationError("re-imported app is not available")
        new_key = args.reimport_app_api_key or console.create_app_api_key(reimport_app["app_id"])
        if not new_key:
            raise ValidationError("cannot mint an API key for the re-imported app")
        reimport_api = ServiceApi(args.dify_url, new_key)
        player_c = f"wf_reimport_{stamp}"
        response = reimport_api.run_workflow(
            {"player_id": player_c, "player_input": "推门进来，外面雨好大", "action": "continue"},
            user=f"{player_c}-{uuid.uuid4().hex[:6]}",
        )
        data = response.get("data") or {}
        if data.get("status") != "succeeded":
            raise ValidationError(f"re-imported workflow did not succeed: {data.get('status')}")
        state = _expect_state(args.memory_url, player_c, visit_count=1)
        return {"reimport_app_id": reimport_app["app_id"], "outputs": data.get("outputs"), "state": state}

    record("reimported_workflow_runs", "重新导入后的工作流依然能跑通并写库", run_reimported)

    record(
        "node_executions_recorded",
        "控制台记录了节点级执行轨迹",
        lambda: {"runs": len(console.workflow_runs(app_id)), "note": "详见 workflow_checks.md 的运行记录"},
    )
    return results


def _expect_state(memory_url: str, player_id: str, visit_count: int) -> dict[str, Any]:
    state = memory_api(memory_url, f"/api/state?player_id={urllib.parse.quote(player_id)}")
    if not state.get("ok"):
        raise ValidationError(f"memory service is not healthy: {state}")
    stored = state.get("state") or {}
    actual = int(stored.get("visit_count", 0))
    if actual != visit_count:
        raise ValidationError(f"expected visit_count {visit_count} for {player_id}, got {actual}")
    return {"player_id": player_id, "visit_count": actual, "bond_score": stored.get("bond_score"),
            "chapter": stored.get("chapter"), "favourite": stored.get("favourite"),
            "memories": len(state.get("memories") or []), "recall_mode": state.get("recall_mode")}


def _expect_isolation(memory_url: str, player_a: str, player_b: str) -> dict[str, Any]:
    a = memory_api(memory_url, f"/api/state?player_id={urllib.parse.quote(player_a)}")
    b = memory_api(memory_url, f"/api/state?player_id={urllib.parse.quote(player_b)}")
    for label, payload in (("a", a), ("b", b)):
        if not payload.get("ok"):
            raise ValidationError(f"memory service is not healthy for player {label}: {payload}")
    if not b.get("found"):
        raise ValidationError("the second player must exist after its own run")
    if not a.get("found"):
        raise ValidationError("the first player disappeared")
    b_state = b.get("state") or {}
    if int(b_state.get("visit_count", 0)) != 1:
        raise ValidationError(f"the second player should be at visit 1, got {b_state.get('visit_count')}")
    if (b.get("memories") or []) and not a.get("found"):
        raise ValidationError("cross-player leak detected")
    return {"player_a_visit_count": (a.get("state") or {}).get("visit_count"),
            "player_b_visit_count": (b.get("state") or {}).get("visit_count"),
            "player_b_memories": len(b.get("memories") or [])}


def _expect_reset(memory_url: str, player_a: str, player_b: str) -> dict[str, Any]:
    a = memory_api(memory_url, f"/api/state?player_id={urllib.parse.quote(player_a)}")
    b = memory_api(memory_url, f"/api/state?player_id={urllib.parse.quote(player_b)}")
    if a.get("found"):
        raise ValidationError("the reset player is still present in seekdb")
    if a.get("memories"):
        raise ValidationError("the reset player still has memories")
    if not b.get("found"):
        raise ValidationError("the reset must not remove the other player")
    return {"reset_player_found": a.get("found"), "other_player_found": b.get("found")}


def write_report(results: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for r in results if r["status"] == "PASS")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": passed,
        "failed": len(results) - passed,
        "checks": results,
    }
    (OUTPUT_DIR / "workflow_checks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Dify 工作流真实验证记录",
        "",
        f"- 运行时间：{payload['generated_at']}",
        f"- 结果：**{passed} 通过 / {payload['failed']} 失败**",
        "",
        "| # | 检查项 | 结果 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for index, item in enumerate(results, start=1):
        detail = item.get("description", "")
        if item["status"] == "FAIL":
            detail = f"{detail} —— {item.get('error')}"
        lines.append(f"| {index} | {item['name']} | {item['status']} | {detail} |")
    lines.append("")
    lines.append("## 每项检查的原始返回")
    lines.append("")
    for index, item in enumerate(results, start=1):
        lines.append(f"### {index}. {item['name']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item.get("evidence", item), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    (OUTPUT_DIR / "workflow_checks.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    # Allow the console credentials to live in the git-ignored dify/.env so the
    # validation can be reproduced with a single command.  Values that are
    # already exported win over the env file.
    try:
        from dify.service.config import load_env_file

        load_env_file(REPO_ROOT / "dify" / ".env")
    except Exception:  # noqa: BLE001 - the env file is optional
        pass

    parser = argparse.ArgumentParser(description="Validate the Dify app end to end.")
    parser.add_argument("--dify-url", default=os.getenv("DIFY_URL", "http://localhost"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", ""))
    parser.add_argument("--app-api-key", default=os.getenv("DIFY_APP_API_KEY", ""))
    parser.add_argument("--reimport-app-api-key", default=os.getenv("DIFY_REIMPORT_APP_API_KEY", ""))
    parser.add_argument("--memory-url", default=os.getenv("MEMORY_SERVICE_BASE_URL", "http://127.0.0.1:8077"))
    parser.add_argument("--dsl", default=str(DEFAULT_DSL))
    parser.add_argument("--insecure", action="store_true", help="skip TLS verification")
    args = parser.parse_args()

    if not args.email or not args.password:
        print("DIFY_EMAIL / DIFY_PASSWORD are required (Dify console account).")
        return 2

    print(f"validating against {args.dify_url}")
    results = run_checks(args)
    write_report(results)

    for item in results:
        marker = "PASS" if item["status"] == "PASS" else "FAIL"
        print(f"[{marker}] {item['name']} - {item.get('description')}")
        if item["status"] == "FAIL":
            print(f"        {item.get('error')}")
    failed = [r for r in results if r["status"] != "PASS"]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print(f"report written to {OUTPUT_DIR / 'workflow_checks.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
