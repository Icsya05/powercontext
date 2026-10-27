"""End-to-end validation of the seekdb-backed NPC memory service.

Every check below talks to a running service over HTTP and asserts on the
response *and* on the rows that come back from seekdb, so the produced
evidence shows that the memory really is stored in the database.

Usage (from the repository root, with the service and seekdb running):

    python dify/validation/service_checks.py --base-url http://127.0.0.1:8077

The report is written to ``dify/validation/service_checks.json`` and
``dify/validation/service_checks.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent

TURN_A1 = {
    "player_input": "我想要一杯热可可",
    "npc_reply": "热可可收到。你是这周第三个在雨里站着不撑伞的人。",
    "choices": ["问问他在淋雨的原因", "再点一杯热可可", "看看窗外的雨", "把伞留给他"],
    "chapter": "雨夜初遇",
    "bond_delta": 2,
    "favourite": "热可可",
    "running_joke": "每次来都说不急，最后都待到打烊",
    "display_name": "夜归人",
}
TURN_A2 = {
    "player_input": "热可可真的能让人不怕雨吗",
    "npc_reply": "不能。但你上次说它像拥抱，我就多烧了一分钟。",
    "choices": ["那我明天还来", "把配方写给我", "问他为什么记得", "再要一杯"],
    "chapter": "热可可与旧雨",
    "bond_delta": 3,
    "favourite": "热可可",
    "running_joke": "每次来都说不急，最后都待到打烊",
    "display_name": "夜归人",
}


class CheckFailure(AssertionError):
    """Raised when a check does not meet its expectation."""


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def wait_for_service(base_url: str, timeout: float = 45.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            status, last = http_json("GET", f"{base_url}/api/health", timeout=5)
            if status == 200:
                return last
        except Exception as exc:  # noqa: BLE001
            last = {"error": str(exc)}
        time.sleep(1.0)
    raise CheckFailure(f"service at {base_url} did not become ready: {last}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_checks(base_url: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    player_a = "validate_player_a"
    player_b = "validate_player_b"
    stamp = datetime.now().strftime("%H%M%S")
    player_a = f"{player_a}_{stamp}"
    player_b = f"{player_b}_{stamp}"

    def record(name: str, description: str, fn: Any) -> None:
        started = time.time()
        try:
            evidence = fn()
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "name": name,
                    "description": description,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                    "duration_ms": int((time.time() - started) * 1000),
                }
            )
            return
        results.append(
            {
                "name": name,
                "description": description,
                "status": "PASS",
                "evidence": evidence,
                "duration_ms": int((time.time() - started) * 1000),
            }
        )

    # 1 ------------------------------------------------------------------
    def check_health() -> dict[str, Any]:
        status, body = http_json("GET", f"{base_url}/api/health")
        if status != 200:
            raise CheckFailure(f"health returned HTTP {status}")
        if not body.get("db", {}).get("ok"):
            raise CheckFailure(f"seekdb is not reachable: {body}")
        return body

    record("health_db_reachable", "服务与 seekdb 均可达", check_health)

    # 2 ------------------------------------------------------------------
    def check_schema() -> dict[str, Any]:
        status, body = http_json("GET", f"{base_url}/api/admin/schema")
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"schema introspection failed: HTTP {status} {body}")
        tables = {t["table_name"] for t in body["schema"]["tables"]}
        for required in ("npc_player", "npc_turn"):
            if required not in tables:
                raise CheckFailure(f"table {required} is missing")
        index_names = {i["index_name"] for i in body["schema"]["indexes"]}
        if "idx_npc_turn_fts" not in index_names:
            raise CheckFailure("full-text index idx_npc_turn_fts is missing")
        return body["schema"]

    record("schema_present", "seekdb 中存在表与中文全文索引", check_schema)

    # 3 ------------------------------------------------------------------
    def check_new_player() -> dict[str, Any]:
        status, body = http_json("GET", f"{base_url}/api/state?player_id={player_a}")
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"state read failed: HTTP {status} {body}")
        if body.get("found") or body.get("is_returning"):
            raise CheckFailure("a brand new player must not report stored memory")
        if body.get("memories"):
            raise CheckFailure("a brand new player must not have recalled memories")
        return {"player_id": player_a, "found": body["found"], "memories": body["memories"]}

    record("new_player_has_no_memory", "新玩家首次访问没有历史记忆", check_new_player)

    # 4 ------------------------------------------------------------------
    def check_write() -> dict[str, Any]:
        status, body = http_json(
            "POST", f"{base_url}/api/turn", {"player_id": player_a, **TURN_A1}
        )
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"turn save failed: HTTP {status} {body}")
        state = body.get("state") or {}
        if int(state.get("visit_count", 0)) != 1:
            raise CheckFailure(f"visit_count should be 1, got {state.get('visit_count')}")
        _, rows = http_json("GET", f"{base_url}/api/admin/turns?player_id={player_a}")
        turns = rows.get("turns") or []
        if len(turns) != 1:
            raise CheckFailure(f"expected 1 stored turn, found {len(turns)}")
        if turns[0].get("player_input") != TURN_A1["player_input"]:
            raise CheckFailure("stored turn does not match what was sent")
        return {"state": state, "stored_turn": turns[0]}

    record("write_turn_persisted_in_seekdb", "对话真实写入 seekdb 并可读回", check_write)

    # 5 ------------------------------------------------------------------
    def check_returning() -> dict[str, Any]:
        status, body = http_json(
            "POST", f"{base_url}/api/turn", {"player_id": player_a, **TURN_A2}
        )
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"second turn failed: {body}")
        _, state_body = http_json("GET", f"{base_url}/api/state?player_id={player_a}")
        state = state_body.get("state") or {}
        if not state_body.get("found"):
            raise CheckFailure("the returning player must be recognised")
        if int(state.get("visit_count", 0)) != 2:
            raise CheckFailure(f"visit_count should be 2, got {state.get('visit_count')}")
        if int(state.get("bond_score", 0)) != 5:
            raise CheckFailure(f"bond_score should be 5, got {state.get('bond_score')}")
        if state.get("favourite") != "热可可":
            raise CheckFailure("favourite item was not remembered")
        if state.get("running_joke") != TURN_A1["running_joke"]:
            raise CheckFailure("the running joke was not remembered")
        if state.get("chapter") != "雨夜初遇" and state.get("chapter") != "热可可与旧雨":
            raise CheckFailure(f"unexpected chapter {state.get('chapter')}")
        return {"state": state, "memories": state_body.get("memories")}

    record("returning_player_recovers_state", "同一玩家再次访问时记忆被恢复", check_returning)

    # 6 ------------------------------------------------------------------
    def check_recall() -> dict[str, Any]:
        # The recall keyword is Chinese, so it has to be percent-encoded before
        # it can go into a request line.
        query = urllib.parse.quote("热可可")
        status, body = http_json(
            "GET", f"{base_url}/api/state?player_id={urllib.parse.quote(player_a)}&query={query}"
        )
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"recall failed: {body}")
        mode = body.get("recall_mode")
        if mode not in ("fulltext", "fulltext-boolean"):
            raise CheckFailure(f"expected a seekdb full-text recall, got mode={mode!r}")
        if not body.get("memories"):
            raise CheckFailure("full-text recall returned no memories")
        return {
            "recall_mode": mode,
            "memories": body["memories"],
            "fts_parser": http_json("GET", f"{base_url}/api/admin/schema")[1]["schema"]["fts_parser"],
        }

    record("memory_recall_uses_seekdb_fts", "中文全文检索从历史对话中召回往事", check_recall)

    # 7 ------------------------------------------------------------------
    def check_isolation() -> dict[str, Any]:
        status, body = http_json("GET", f"{base_url}/api/state?player_id={player_b}")
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"isolation read failed: {body}")
        if body.get("found"):
            raise CheckFailure("player B must not see player A's state")
        if body.get("memories"):
            raise CheckFailure("player B must not see player A's memories")
        _, a_body = http_json("GET", f"{base_url}/api/state?player_id={player_a}")
        if not a_body.get("found"):
            raise CheckFailure("player A's state disappeared")
        return {"player_b": body, "player_a_still_present": a_body.get("found")}

    record("players_are_isolated", "不同玩家之间数据完全隔离", check_isolation)

    # 8 ------------------------------------------------------------------
    def check_reset() -> dict[str, Any]:
        status, body = http_json("DELETE", f"{base_url}/api/state?player_id={player_a}")
        if status != 200 or not body.get("ok"):
            raise CheckFailure(f"reset failed: {body}")
        if int(body.get("deleted_turns", 0)) < 2:
            raise CheckFailure(f"reset should have removed 2 turns, removed {body.get('deleted_turns')}")
        _, after = http_json("GET", f"{base_url}/api/state?player_id={player_a}")
        if after.get("found"):
            raise CheckFailure("state still present after reset")
        if after.get("memories"):
            raise CheckFailure("memories still present after reset")
        _, b_after = http_json("GET", f"{base_url}/api/state?player_id={player_b}")
        if b_after.get("found"):
            raise CheckFailure("reset must not touch another player")
        return {"reset": body, "player_a_after": after}

    record("reset_only_affects_target", "重置只清除目标玩家，其他玩家不受影响", check_reset)

    # 9 ------------------------------------------------------------------
    def check_invalid_id() -> dict[str, Any]:
        status, body = http_json("GET", f"{base_url}/api/state?player_id=bad%20id%21")
        if status != 200:
            raise CheckFailure(f"expected HTTP 200 with an error body, got {status}")
        if body.get("code") != "INVALID_PLAYER_ID":
            raise CheckFailure(f"expected INVALID_PLAYER_ID, got {body.get('code')}")
        return body

    record("invalid_player_id_rejected", "非法玩家标识被明确拒绝", check_invalid_id)

    # 10 -----------------------------------------------------------------
    def check_db_down() -> dict[str, Any]:
        """Start a second instance pointed at a dead port and prove the error."""
        port = free_port()
        env = dict(os.environ)
        env.update(
            {
                "SEEKDB_HOST": "127.0.0.1",
                "SEEKDB_PORT": str(port),
                "SEEKDB_CONNECT_TIMEOUT": "3",
            }
        )
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "dify.service.app:app",
             "--host", "127.0.0.1", "--port", str(port + 1), "--app-dir", str(REPO_ROOT)],
            env=env,
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead_url = f"http://127.0.0.1:{port + 1}"
        try:
            wait_for_service(dead_url, timeout=45)
            status, body = http_json("GET", f"{dead_url}/api/state?player_id=probe_player")
            if status != 200:
                raise CheckFailure(f"expected HTTP 200, got {status}")
            if body.get("ok") is not False:
                raise CheckFailure("service must not claim success when seekdb is down")
            if body.get("code") != "DB_UNAVAILABLE":
                raise CheckFailure(f"expected DB_UNAVAILABLE, got {body.get('code')}")
            if not body.get("message"):
                raise CheckFailure("a readable error message is required")
            _, health = http_json("GET", f"{dead_url}/api/health")
            if health.get("db", {}).get("ok"):
                raise CheckFailure("health must report the database as down")
            return {"error_body": body, "health": health, "dead_port": port}
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    record("db_unavailable_returns_clear_error", "数据库不可用时返回明确错误而非伪造成功", check_db_down)

    return results


def write_report(results: list[dict[str, Any]], base_url: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for r in results if r["status"] == "PASS")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "passed": passed,
        "failed": len(results) - passed,
        "checks": results,
    }
    (OUTPUT_DIR / "service_checks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# seekdb 记忆服务验证记录",
        "",
        f"- 运行时间：{payload['generated_at']}",
        f"- 服务地址：`{base_url}`",
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
    (OUTPUT_DIR / "service_checks.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the NPC memory service against seekdb.")
    parser.add_argument("--base-url", default=os.getenv("MEMORY_SERVICE_BASE_URL", "http://127.0.0.1:8077"))
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    print(f"validating {base_url}")
    results = run_checks(base_url)
    write_report(results, base_url)

    for item in results:
        marker = "PASS" if item["status"] == "PASS" else "FAIL"
        print(f"[{marker}] {item['name']} - {item.get('description')}")
        if item["status"] == "FAIL":
            print(f"        {item.get('error')}")
    failed = [r for r in results if r["status"] != "PASS"]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print(f"report written to {OUTPUT_DIR / 'service_checks.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
