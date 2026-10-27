"""Static validation of the Dify DSL in ``dify/workflow.yml``.

This does not replace importing into a real Dify instance - it catches the
mistakes that are cheap to make when the DSL is hand written:

* the YAML must parse and the top level must look like a Dify app export;
* every edge must connect nodes that exist;
* every node must be reachable from the start node and reach an end node;
* every code node body must be syntactically valid Python;
* every ``{{#node.variable#}}`` reference must point at a node that exists and
  (for code nodes) at an output that node actually declares.

Usage (from the repository root):

    python dify/deploy/check_dsl.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DSL = REPO_ROOT / "dify" / "workflow.yml"

VARIABLE_RE = re.compile(r"\{\{#([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)#\}\}")


def load_dsl(path: Path) -> dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def check(dsl: dict[str, Any]) -> list[str]:
    """Return a list of problems; an empty list means the DSL looks sound."""
    problems: list[str] = []

    for key in ("app", "kind", "version", "workflow"):
        if key not in dsl:
            problems.append(f"missing top level key: {key}")
    if dsl.get("kind") != "app":
        problems.append(f"kind must be 'app', got {dsl.get('kind')!r}")

    workflow = dsl.get("workflow") or {}
    graph = workflow.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        problems.append("workflow.graph.nodes is empty")
        return problems

    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id"))
        if node_id in by_id:
            problems.append(f"duplicate node id: {node_id}")
        by_id[node_id] = node

    # --- edges ---------------------------------------------------------
    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source not in by_id:
            problems.append(f"edge {edge.get('id')}: unknown source node {source!r}")
        if target not in by_id:
            problems.append(f"edge {edge.get('id')}: unknown target node {target!r}")
        handle = str(edge.get("sourceHandle") or "")
        if handle and handle not in ("source", "true", "false"):
            problems.append(f"edge {edge.get('id')}: unexpected sourceHandle {handle!r}")

    # --- start / end ----------------------------------------------------
    starts = [n for n in nodes if (n.get("data") or {}).get("type") == "start"]
    ends = [n for n in nodes if (n.get("data") or {}).get("type") == "end"]
    if len(starts) != 1:
        problems.append(f"expected exactly one start node, found {len(starts)}")
    if not ends:
        problems.append("no end node found")

    # --- reachability ---------------------------------------------------
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    incoming: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source in outgoing and target in incoming:
            outgoing[source].append(target)
            incoming[target].append(source)

    if starts:
        seen: set[str] = set()
        stack = [str(starts[0].get("id"))]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(outgoing.get(current, []))
        unreachable = sorted(set(by_id) - seen)
        if unreachable:
            problems.append(f"nodes not reachable from start: {unreachable}")

        terminal = {str(end.get("id")) for end in ends}
        # every node must be able to reach an end node
        can_reach_end: set[str] = set()
        stack = list(terminal)
        while stack:
            current = stack.pop()
            if current in can_reach_end:
                continue
            can_reach_end.add(current)
            stack.extend(incoming.get(current, []))
        dead = sorted(set(by_id) - can_reach_end)
        if dead:
            problems.append(f"nodes that cannot reach an end node: {dead}")

    # --- code nodes -----------------------------------------------------
    for node in nodes:
        data = node.get("data") or {}
        if data.get("type") != "code":
            continue
        node_id = str(node.get("id"))
        code = data.get("code") or ""
        try:
            compile(code, f"<{node_id}>", "exec")
        except SyntaxError as exc:
            problems.append(f"code node {node_id} has invalid Python: {exc}")
        if "def main(" not in code:
            problems.append(f"code node {node_id} does not define main()")
        outputs = data.get("outputs") or {}
        if not outputs:
            problems.append(f"code node {node_id} declares no outputs")
        declared = {str(name) for name in outputs}
        inputs = {str(v.get("variable")) for v in (data.get("variables") or [])}
        # Every declared input must be a parameter of main(), otherwise Dify
        # passes a keyword argument the function does not accept.
        parameters = set(re.findall(r"def\s+main\s*\(([^)]*)\)", code, flags=re.DOTALL))
        accepted: set[str] = set()
        for group in parameters:
            for chunk in group.split(","):
                name = chunk.split(":")[0].split("=")[0].strip()
                if name:
                    accepted.add(name)
        missing = inputs - accepted
        if missing:
            problems.append(
                f"code node {node_id} declares inputs that main() does not accept: {sorted(missing)}"
            )

        # Actually run the node with its default arguments and check that it
        # returns exactly the declared outputs.  This catches logic that would
        # blow up inside Dify's sandbox.
        try:
            namespace: dict[str, Any] = {}
            exec(compile(code, f"<{node_id}>", "exec"), namespace)  # noqa: S102
            main = namespace.get("main")
            if not callable(main):
                problems.append(f"code node {node_id} does not expose a callable main()")
            else:
                produced = main()
                if not isinstance(produced, dict):
                    problems.append(f"code node {node_id} main() did not return a dict")
                else:
                    returned = {str(key) for key in produced}
                    if returned != declared:
                        problems.append(
                            f"code node {node_id} returns {sorted(returned)} but declares {sorted(declared)}"
                        )
        except Exception as exc:  # noqa: BLE001
            problems.append(f"code node {node_id} raised while running main(): {type(exc).__name__}: {exc}")

    # --- variable references -------------------------------------------
    for node in nodes:
        data = node.get("data") or {}
        node_id = str(node.get("id"))
        blob_parts: list[str] = []
        for key in ("url", "headers", "params", "answer"):
            if isinstance(data.get(key), str):
                blob_parts.append(data[key])
        body = data.get("body")
        if isinstance(body, dict) and isinstance(body.get("data"), str):
            blob_parts.append(body["data"])
        for prompt in data.get("prompt_template") or []:
            if isinstance(prompt, dict) and isinstance(prompt.get("text"), str):
                blob_parts.append(prompt["text"])
        blob = "\n".join(blob_parts)
        for ref_node, ref_var in VARIABLE_RE.findall(blob):
            if ref_node not in by_id:
                problems.append(f"node {node_id} references unknown node {ref_node!r}")
                continue
            target_data = by_id[ref_node].get("data") or {}
            target_type = target_data.get("type")
            if target_type == "code":
                outputs = {str(name) for name in (target_data.get("outputs") or {})}
                if ref_var not in outputs:
                    problems.append(
                        f"node {node_id} references {ref_node}.{ref_var} which is not an output of that code node"
                    )
            elif target_type == "http-request":
                if ref_var not in ("body", "status_code", "headers", "files"):
                    problems.append(
                        f"node {node_id} references {ref_node}.{ref_var} which is not an http-request output"
                    )
            elif target_type == "llm":
                if ref_var != "text":
                    problems.append(
                        f"node {node_id} references {ref_node}.{ref_var} but the llm node only exposes 'text'"
                    )

    # --- start variables -------------------------------------------------
    for node in starts:
        data = node.get("data") or {}
        variables = data.get("variables") or []
        names = [str(v.get("variable")) for v in variables]
        if len(names) != len(set(names)):
            problems.append("start node has duplicate variable names")
        for variable in variables:
            if not variable.get("required"):
                problems.append(
                    f"start variable {variable.get('variable')!r} should be required for a reproducible run"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Static check of the Dify DSL.")
    parser.add_argument("--dsl", default=str(DEFAULT_DSL))
    args = parser.parse_args()

    path = Path(args.dsl)
    print(f"checking {path}")
    try:
        dsl = load_dsl(path)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to parse YAML: {exc}")
        return 2

    problems = check(dsl)
    if problems:
        print(f"{len(problems)} problem(s) found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    graph = dsl["workflow"]["graph"]
    print(f"DSL OK: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
    for node in graph["nodes"]:
        print(f"  {node['id']:<22} {(node.get('data') or {}).get('type')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
