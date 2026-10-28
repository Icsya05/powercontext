"""Produce the reviewer facing evidence artefacts.

* ``code-diff.patch``      - the unified diff of the delivered change
* ``state-from-powercontext.json`` - the task state read back from PowerContext
* ``seekdb-queries.md``    - the seekdb statements the module really ran
* ``minimax-usage.md``     - the MiniMax calls with their token usage
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sddctx.config import EVIDENCE_DIR, load_config  # noqa: E402
from sddctx.powercontext_client import PowerContextClient  # noqa: E402
from sddctx.runner import load_task  # noqa: E402
from sddctx.seekdb_store import SeekDBStore  # noqa: E402

TASK_ID = "T-2026-001"
MINIMAX_DIR = EVIDENCE_DIR.parent


def all_records() -> list[dict]:
    records = []
    raw_dir = EVIDENCE_DIR / "raw"
    if not raw_dir.is_dir():
        return records
    for path in sorted(raw_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def write_code_diff() -> Path:
    before_root = MINIMAX_DIR / "sample_project" / "before" / "jmespath"
    after_root = MINIMAX_DIR / "sample_project" / "jmespath" / "jmespath"
    chunks: list[str] = []
    for path in sorted(before_root.rglob("*.py")):
        relative = path.relative_to(before_root)
        after = after_root / relative
        if not after.is_file():
            continue
        before_text = path.read_text(encoding="utf-8").splitlines(keepends=True)
        after_text = after.read_text(encoding="utf-8").splitlines(keepends=True)
        if before_text == after_text:
            continue
        chunks.extend(
            difflib.unified_diff(
                before_text,
                after_text,
                fromfile=f"a/minimax/sample_project/before/jmespath/{relative.as_posix()}",
                tofile=f"b/minimax/sample_project/jmespath/jmespath/{relative.as_posix()}",
                n=3,
            )
        )
    target = EVIDENCE_DIR / "code-diff.patch"
    target.write_text("".join(chunks), encoding="utf-8")
    return target


def write_state(config) -> Path:
    client = PowerContextClient(config.powercontext)
    task = load_task(TASK_ID, config)
    scope = client.find_scope(TASK_ID)
    state = None
    if scope is not None:
        state = client.load_state(scope.scope_id, TASK_ID)
    payload = {
        "scope_id": scope.scope_id if scope else None,
        "scope_title": scope.title if scope else None,
        "task_id": TASK_ID,
        "state": state,
    }
    target = EVIDENCE_DIR / "state-from-powercontext.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_seekdb_queries() -> Path:
    records = [r for r in all_records() if r.get("kind") == "seekdb.query"]
    seen: set[str] = set()
    lines = [
        "# seekdb 查询记录",
        "",
        f"模块一共执行了 {len(records)} 条 seekdb 语句。",
        "下面是去重后的语句（每条附一次真实执行的结果行数）。",
        "",
    ]
    for record in records:
        sql = " ".join((record.get("sql") or "").split())
        if sql in seen:
            continue
        seen.add(sql)
        lines.append(f"## rows={record.get('rows')}  mode={record.get('mode')}")
        lines.append("")
        lines.append("```sql")
        lines.append(sql)
        lines.append("```")
        lines.append("")
        params = record.get("params") or []
        if params:
            preview = [p if len(str(p)) <= 80 else str(p)[:77] + "..." for p in params]
            lines.append(f"参数（截断）：`{json.dumps(preview, ensure_ascii=False)}`")
            lines.append("")
    target = EVIDENCE_DIR / "seekdb-queries.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def write_minimax_usage() -> Path:
    records = [r for r in all_records() if r.get("kind") in {"minimax.call", "patch.requested", "testgen.requested"}]
    lines = [
        "# MiniMax 开发记录",
        "",
        "下表是模块实际发出的 MiniMax 调用。`request_id` 来自 MiniMax 服务端，",
        "`usage` 是服务端返回的 token 用量。",
        "",
        "| 时间 | 类型 | request_id | 模型 | usage |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        usage = record.get("usage") or {}
        lines.append(
            f"| {record.get('at')} | {record.get('kind')} | `{record.get('request_id', '')}` "
            f"| {record.get('model', '')} | `{json.dumps(usage, ensure_ascii=False)}` |"
        )
    lines.append("")
    lines.append("## 每次调用的提问与回答")
    lines.append("")
    for record in records:
        if record.get("kind") != "minimax.call":
            continue
        lines.append(f"### {record.get('at')}  `{record.get('request_id', '')}`")
        lines.append("")
        answer = record.get("answer") or ""
        lines.append("回答（截断到 3000 字符）：")
        lines.append("")
        lines.append("```")
        lines.append(answer[:3000])
        lines.append("```")
        lines.append("")
    target = EVIDENCE_DIR / "minimax-usage.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def main() -> int:
    config = load_config()
    targets = [
        write_code_diff(),
        write_state(config),
        write_seekdb_queries(),
        write_minimax_usage(),
    ]
    for target in targets:
        print(f"wrote {target.as_posix()} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
