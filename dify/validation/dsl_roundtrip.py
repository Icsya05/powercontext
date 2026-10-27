"""Validate the DSL round trip against a live Dify 1.17.1 console.

This is the part of the deliverable that can be verified **without** a model
provider: the workflow DSL that ships in ``dify/workflow.yml`` must import into
Dify, survive a publish, be exported again, and be importable into a *clean*
application with an identical graph.

What is checked:

1. login to the Dify console;
2. import ``dify/workflow.yml``;
3. publish the workflow and enable its API;
4. export the DSL back out of Dify;
5. compare the exported graph with the source graph (nodes, edges, ids, types,
   the LLM node's model wiring);
6. import the **exported** DSL into a brand new application;
7. export that second application again and prove the two exports are
   identical - i.e. the round trip is stable and reproducible.

Usage (from the repository root):

    python dify/validation/dsl_roundtrip.py \\
        --dify-url http://localhost --email ... --password ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dify.validation.workflow_checks import Console, ValidationError  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_DSL = REPO_ROOT / "dify" / "workflow.yml"


def graph_of(dsl_text: str) -> dict[str, Any]:
    data = yaml.safe_load(dsl_text)
    if not isinstance(data, dict):
        raise ValidationError("DSL is not a mapping")
    graph = (data.get("workflow") or {}).get("graph") or {}
    return graph


def fingerprint(graph: dict[str, Any]) -> dict[str, Any]:
    """A comparable summary of a workflow graph."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_rows = []
    for node in nodes:
        data = node.get("data") or {}
        node_rows.append(
            {
                "id": node.get("id"),
                "type": data.get("type"),
                "title": data.get("title"),
                "model_provider": (data.get("model") or {}).get("provider"),
                "model_name": (data.get("model") or {}).get("name"),
                "url": data.get("url"),
                "method": data.get("method"),
            }
        )
    edge_rows = [
        {"source": edge.get("source"), "target": edge.get("target"), "sourceHandle": edge.get("sourceHandle")}
        for edge in edges
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": node_rows,
        "edges": edge_rows,
    }


def diff_fingerprints(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Human readable differences between two graph fingerprints."""
    problems: list[str] = []
    if a["node_count"] != b["node_count"]:
        problems.append(f"node count {a['node_count']} != {b['node_count']}")
    if a["edge_count"] != b["edge_count"]:
        problems.append(f"edge count {a['edge_count']} != {b['edge_count']}")

    by_id_a = {row["id"]: row for row in a["nodes"]}
    by_id_b = {row["id"]: row for row in b["nodes"]}
    for node_id, row_a in by_id_a.items():
        row_b = by_id_b.get(node_id)
        if row_b is None:
            problems.append(f"node {node_id} missing in the second graph")
            continue
        for key in ("type", "title", "model_provider", "model_name", "url", "method"):
            if row_a.get(key) != row_b.get(key):
                problems.append(
                    f"node {node_id}.{key}: {row_a.get(key)!r} != {row_b.get(key)!r}"
                )
    for node_id in by_id_b:
        if node_id not in by_id_a:
            problems.append(f"node {node_id} only exists in the second graph")

    edges_a = {(e["source"], e["sourceHandle"], e["target"]) for e in a["edges"]}
    edges_b = {(e["source"], e["sourceHandle"], e["target"]) for e in b["edges"]}
    for edge in sorted(edges_a - edges_b, key=lambda e: tuple(str(x) for x in e)):
        problems.append(f"edge {edge} missing in the second graph")
    for edge in sorted(edges_b - edges_a, key=lambda e: tuple(str(x) for x in e)):
        problems.append(f"edge {edge} only exists in the second graph")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Dify DSL round trip.")
    parser.add_argument("--dify-url", default=os.getenv("DIFY_URL", "http://localhost"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", ""))
    parser.add_argument("--dsl", default=str(DEFAULT_DSL))
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    # Allow the console credentials to live in the git-ignored dify/.env so the
    # round trip can be reproduced with a single command.
    if not args.email or not args.password:
        try:
            from dify.service.config import load_env_file

            load_env_file(REPO_ROOT / "dify" / ".env")
            args.email = args.email or os.getenv("DIFY_EMAIL", "")
            args.password = args.password or os.getenv("DIFY_PASSWORD", "")
        except Exception:  # noqa: BLE001 - the env file is optional
            pass

    if not args.email or not args.password:
        print("DIFY_EMAIL / DIFY_PASSWORD are required (Dify console account).")
        return 2
    console = Console(args.dify_url, insecure=args.insecure)
    results: list[dict[str, Any]] = []

    def record(name: str, description: str, fn) -> None:
        try:
            evidence = fn()
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"name": name, "description": description, "status": "FAIL",
                 "error": f"{type(exc).__name__}: {exc}"}
            )
            print(f"[FAIL] {name} - {description}\n        {type(exc).__name__}: {exc}")
            return
        results.append({"name": name, "description": description, "status": "PASS", "evidence": evidence})
        print(f"[PASS] {name} - {description}")

    dsl_text = Path(args.dsl).read_text(encoding="utf-8")
    source_fp = fingerprint(graph_of(dsl_text))

    record("console_login", "登录 Dify 控制台", lambda: (console.login(args.email, args.password),
                                                         {"email": args.email, "csrf": bool(console.csrf)})[1])

    holder: dict[str, str] = {}

    def do_import() -> dict[str, Any]:
        app_id = console.import_dsl(dsl_text)
        holder["app_id"] = app_id
        return {"app_id": app_id, "dsl_bytes": len(dsl_text.encode("utf-8"))}

    record("dsl_import", "把 workflow.yml 导入 Dify", do_import)
    if "app_id" not in holder:
        _write_report(results)
        return 1
    app_id = holder["app_id"]

    record(
        "publish_and_enable_api",
        "发布工作流并开启 API 访问",
        lambda: {"published": console.publish(app_id), "api_enabled": console.enable_api(app_id)},
    )

    exported: dict[str, str] = {}

    def do_export() -> dict[str, Any]:
        text = console.export_dsl(app_id)
        exported["first"] = text
        data = yaml.safe_load(text)
        return {
            "export_bytes": len(text.encode("utf-8")),
            "dsl_version": data.get("version"),
            "app_mode": (data.get("app") or {}).get("mode"),
            "nodes": len((data.get("workflow") or {}).get("graph", {}).get("nodes", [])),
            "edges": len((data.get("workflow") or {}).get("graph", {}).get("edges", [])),
        }

    record("dsl_export", "从 Dify 导出 DSL", do_export)

    def do_compare() -> dict[str, Any]:
        if "first" not in exported:
            raise ValidationError("no exported DSL to compare")
        exported_fp = fingerprint(graph_of(exported["first"]))
        problems = diff_fingerprints(source_fp, exported_fp)
        if problems:
            raise ValidationError("; ".join(problems))
        return {
            "source_nodes": source_fp["node_count"],
            "source_edges": source_fp["edge_count"],
            "exported_nodes": exported_fp["node_count"],
            "exported_edges": exported_fp["edge_count"],
            "llm_node": [row for row in exported_fp["nodes"] if row["type"] == "llm"],
            "http_nodes": [row for row in exported_fp["nodes"] if row["type"] == "http-request"],
        }

    record("export_matches_source", "导出的 DSL 与源文件图结构一致", do_compare)

    reimport: dict[str, str] = {}

    def do_reimport() -> dict[str, Any]:
        if "first" not in exported:
            raise ValidationError("nothing to re-import")
        new_app_id = console.import_dsl(exported["first"])
        reimport["app_id"] = new_app_id
        console.publish(new_app_id)
        console.enable_api(new_app_id)
        return {"new_app_id": new_app_id}

    record("dsl_reimport_clean_app", "把导出的 DSL 导入一个干净的新应用", do_reimport)

    def do_stable() -> dict[str, Any]:
        if "app_id" not in reimport:
            raise ValidationError("the re-imported app is not available")
        second = console.export_dsl(reimport["app_id"])
        if second.strip() != exported["first"].strip():
            fp1 = fingerprint(graph_of(exported["first"]))
            fp2 = fingerprint(graph_of(second))
            problems = diff_fingerprints(fp1, fp2)
            raise ValidationError(
                "the two exports differ: " + ("; ".join(problems) if problems else "byte level difference")
            )
        return {
            "identical": True,
            "bytes": len(second.encode("utf-8")),
            "app_id": reimport["app_id"],
        }

    record("reimported_export_identical", "重新导入后再导出与第一次导出逐字节一致", do_stable)

    _write_report(results)
    failed = [r for r in results if r["status"] != "PASS"]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print(f"report written to {OUTPUT_DIR / 'dsl_roundtrip.md'}")
    return 1 if failed else 0


def _write_report(results: list[dict[str, Any]]) -> None:
    passed = sum(1 for r in results if r["status"] == "PASS")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": passed,
        "failed": len(results) - passed,
        "checks": results,
    }
    (OUTPUT_DIR / "dsl_roundtrip.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Dify DSL 往返验证记录（导入 → 发布 → 导出 → 重导入 → 再导出）",
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
    lines.extend(["", "## 每项检查的原始返回", ""])
    for index, item in enumerate(results, start=1):
        lines.append(f"### {index}. {item['name']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item.get("evidence", item), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    (OUTPUT_DIR / "dsl_roundtrip.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
