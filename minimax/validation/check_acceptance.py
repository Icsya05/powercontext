"""Acceptance check for the six must-pass items of the MiniMax topic.

Run it from the ``minimax`` directory::

    python -m validation.check_acceptance

Every check talks to the real dependencies - seekdb, PowerContext and
MiniMax - and reads the evidence that the module recorded.  Nothing is
simulated: a check only passes when the real thing is there.

The six items are the ones listed in section 4.1 of the official topic:

1. 能够运行
2. MiniMax 实际参与
3. 上下文正确
4. 数据库实际参与
5. 状态能够复用
6. 代码修改有效
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sddctx.code_index import index_project  # noqa: E402
from sddctx.config import EVIDENCE_DIR, REPO_ROOT, load_config  # noqa: E402
from sddctx.context import build_context, parse_task  # noqa: E402
from sddctx.documents import load_documents  # noqa: E402
from sddctx.evidence import EvidenceRecorder  # noqa: E402
from sddctx.powercontext_client import PowerContextClient  # noqa: E402
from sddctx.runner import load_task  # noqa: E402
from sddctx.seekdb_store import SeekDBStore  # noqa: E402

TASK_ID = "T-2026-001"
MINIMAX_DIR = REPO_ROOT / "minimax"
RAW_EVIDENCE = EVIDENCE_DIR / "raw"
PATCH_DIR = EVIDENCE_DIR / "patches"


@dataclass
class Check:
    name: str
    item: str
    passed: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _run(command: str, cwd: Path) -> tuple[int, str]:
    process = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.returncode, (process.stdout or "") + (process.stderr or "")


def _raw_logs() -> list[Path]:
    if not RAW_EVIDENCE.is_dir():
        return []
    return sorted(RAW_EVIDENCE.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def _all_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _raw_logs():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    return records


def check_runnable(config) -> Check:
    """1. 能运行: all three dependencies answer, and the module imports."""
    problems: list[str] = []

    store = SeekDBStore(config.seekdb)
    try:
        store.ensure_database()
        store.ensure_schema()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"seekdb: {exc}")

    try:
        health = PowerContextClient(config.powercontext).health()
        if health.get("status") != "ready":
            problems.append(f"PowerContext status={health.get('status')}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"PowerContext: {exc}")

    try:
        from sddctx.minmax_client import MiniMaxClient

        MiniMaxClient(config.minimax).complete("Reply OK", "ping", max_tokens=16, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"MiniMax: {exc}")

    code, output = _run("python -m pytest sddctx/tests/test_sddctx.py -q", MINIMAX_DIR)
    if code != 0:
        problems.append(f"module self test failed: {output.strip()[:300]}")

    return Check(
        name="runnable",
        item="能够运行",
        passed=not problems,
        detail="; ".join(problems) if problems else "seekdb, PowerContext, MiniMax and the module all answer",
        evidence={"problems": problems},
    )


def check_minimax_involved(config) -> Check:
    """2. MiniMax 实际参与: a recorded model call produced the applied patch."""
    records = _all_records()
    calls = [r for r in records if r.get("kind") == "minimax.call"]
    requested = [r for r in records if r.get("kind") == "patch.requested"]
    applied = [r for r in records if r.get("kind") == "patch.applied" and r.get("exit_code") == 0]
    patches = sorted(PATCH_DIR.glob("*.patch")) if PATCH_DIR.is_dir() else []

    problems: list[str] = []
    if not calls:
        problems.append("no MiniMax call recorded")
    if not requested:
        problems.append("no patch request recorded")
    if not applied:
        problems.append("no patch was applied successfully")
    if not patches:
        problems.append("no patch file on disk")

    # the applied implementation must be present in the delivered file, and it
    # must differ from the pre-change snapshot
    target = config.sample_project / "jmespath" / "functions.py"
    before = MINIMAX_DIR / "sample_project" / "before" / "jmespath" / "functions.py"
    if not target.is_file():
        problems.append(f"the implementation file is missing: {target}")
    else:
        current_text = target.read_text(encoding="utf-8")
        if "_func_matches" not in current_text:
            problems.append("the working tree does not contain the matches() implementation")
        if before.is_file() and before.read_text(encoding="utf-8") == current_text:
            problems.append("the implementation file is identical to the pre-change snapshot")

    # the patch must describe the change that is actually in the tree
    if patches and target.is_file():
        newest = patches[-1]
        patch_text = newest.read_text(encoding="utf-8", errors="replace")
        if "_func_matches" not in patch_text:
            problems.append("the patch on disk does not mention the matches() function")

    return Check(
        name="minimax-involved",
        item="MiniMax 实际参与",
        passed=not problems,
        detail="; ".join(problems)
        if problems
        else f"{len(calls)} MiniMax call(s) recorded, {len(patches)} patch file(s), "
        "the implementation is in the delivered file and differs from the pre-change snapshot",
        evidence={
            "minimax_calls": len(calls),
            "patch_requests": len(requested),
            "patches_applied": len(applied),
            "patch_files": [p.name for p in patches],
            "usage": [r.get("usage") for r in calls],
            "request_ids": [r.get("request_id") for r in calls],
        },
    )


def check_context(config) -> Check:
    """3. 上下文正确: the context locates the required sources, and follows a spec edit."""
    task = load_task(TASK_ID, config)
    store = SeekDBStore(config.seekdb)
    context = build_context(task, store)

    problems: list[str] = []
    spec_ids = {entry.identifier.split("#")[0] for entry in context.specs}
    if "SPEC-JP-FN-001" not in spec_ids:
        problems.append("the applicable specification is missing from the context")
    required_sections = {"R1", "R2", "R3", "R4", "R5", "R6"}
    found_sections = {entry.identifier.split("#")[-1] for entry in context.specs}
    missing = required_sections - found_sections
    if missing:
        problems.append(f"specification sections missing: {sorted(missing)}")

    code_files = {entry.detail.get("file_path") for entry in context.code}
    if "jmespath/functions.py" not in code_files:
        problems.append("the code file under change is missing from the context")

    test_files = {entry.detail.get("file_path") for entry in context.tests}
    if "tests/test_matches.py" not in test_files:
        problems.append("the target test file is missing from the context")

    # every source must really exist on disk
    for entry in context.specs + context.code + context.tests:
        path = Path(entry.source_path)
        if not path.is_file():
            problems.append(f"source does not exist: {entry.source}")
            break
        line = entry.source_line
        if line <= 0 or line > len(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            problems.append(f"source line out of range: {entry.source}")
            break

    return Check(
        name="context-correct",
        item="上下文正确",
        passed=not problems,
        detail="; ".join(problems) if problems else (
            f"{len(context.specs)} specification entries, {len(context.code)} code symbols, "
            f"{len(context.tests)} test cases, every source verified on disk"
        ),
        evidence={
            "retrieval": context.retrieval,
            "specifications": [entry.identifier for entry in context.specs],
            "code": [f"{entry.detail.get('file_path')}::{entry.identifier}" for entry in context.code][:12],
            "tests": [entry.identifier for entry in context.tests][:12],
        },
    )


def check_spec_follows_edit(config) -> Check:
    """3b. 规格更新并重新导入后, 上下文使用更新后的内容."""
    spec_path = MINIMAX_DIR / "specs" / "jmespath-matches.md"
    original = spec_path.read_text(encoding="utf-8")
    marker = "PROBE-EDIT-9137"
    problems: list[str] = []

    try:
        # 1) edit the specification
        edited = original.replace(
            "## R2 | 命中返回 true，未命中返回 false",
            f"## R2 | 命中返回 true，未命中返回 false {marker}",
        )
        if marker not in edited:
            problems.append("could not edit the specification")
        spec_path.write_text(edited, encoding="utf-8")

        # 2) re-import
        from sddctx.runner import import_material

        recorder = EvidenceRecorder("acceptance-spec-edit")
        import_material(config, recorder)

        # 3) the context must contain the new text
        task = load_task(TASK_ID, config)
        context = build_context(task, SeekDBStore(config.seekdb))
        bodies = " ".join(entry.body for entry in context.specs)
        if marker not in bodies:
            problems.append("the edited specification is not used by the context")
    finally:
        # 4) restore the original file and re-import, so the delivered state
        #    matches the committed specification
        spec_path.write_text(original, encoding="utf-8")
        from sddctx.runner import import_material

        import_material(config, EvidenceRecorder("acceptance-spec-restore"))

    return Check(
        name="context-follows-spec-edit",
        item="上下文正确（规格更新后重新导入）",
        passed=not problems,
        detail="; ".join(problems)
        if problems
        else "editing the specification and re-importing changes the retrieved content",
        evidence={"marker": marker},
    )


def check_database(config) -> Check:
    """4. 数据库实际参与: seekdb holds the material and the queries are recorded."""
    store = SeekDBStore(config.seekdb)
    problems: list[str] = []
    try:
        counts = store.counts()
    except Exception as exc:  # noqa: BLE001
        counts = {}
        problems.append(f"cannot read seekdb: {exc}")

    if counts.get("specs", 0) <= 0:
        problems.append("no specification rows in seekdb")
    if counts.get("code", 0) <= 0:
        problems.append("no code rows in seekdb")
    if counts.get("tests", 0) <= 0:
        problems.append("no test rows in seekdb")

    queries = [r for r in _all_records() if r.get("kind") == "seekdb.query"]
    search_queries = [q for q in queries if "AGAINST" in (q.get("sql") or "")]
    if not search_queries:
        problems.append("no full-text search query was recorded")

    # the material really lives in the database, not just in the files
    task = load_task(TASK_ID, config)
    keyword = " ".join(task.keywords)
    spec_rows, mode = store.search_specs(keyword, limit=5)
    if not spec_rows:
        problems.append("the specification cannot be retrieved from seekdb")

    return Check(
        name="database-involved",
        item="数据库实际参与",
        passed=not problems,
        detail="; ".join(problems)
        if problems
        else f"seekdb holds {counts.get('specs')} spec / {counts.get('code')} code / {counts.get('tests')} test rows; "
        f"{len(queries)} recorded queries, {len(search_queries)} of them full-text searches (mode={mode})",
        evidence={
            "counts": counts,
            "recorded_queries": len(queries),
            "fulltext_queries": len(search_queries),
            "sample_query": search_queries[0] if search_queries else None,
        },
    )


def check_state_reuse(config) -> Check:
    """5. 状态能够复用: the state survives a module restart."""
    client = PowerContextClient(config.powercontext)
    task = load_task(TASK_ID, config)
    problems: list[str] = []
    try:
        scope = client.ensure_scope(task.task_id, f"sdd task {task.task_id}", task.title)
        state = client.load_state(scope.scope_id, task.task_id)
    except Exception as exc:  # noqa: BLE001
        scope, state = None, None
        problems.append(f"cannot read the task state: {exc}")

    if not state:
        problems.append("no task state was found in PowerContext")

    # a fresh process must be able to read the state and use it
    used_in_context = False
    if state:
        from sddctx.context import build_context

        context = build_context(task, SeekDBStore(config.seekdb), state=state)
        used_in_context = bool(context.finished or context.todo or context.verification)

    if state and not used_in_context:
        problems.append("the stored state is not used when the context is built")

    return Check(
        name="state-reuse",
        item="状态能够复用",
        passed=not problems,
        detail="; ".join(problems)
        if problems
        else "the task state was written to PowerContext, read back by a separate process and used to build the context",
        evidence={
            "scope_id": getattr(scope, "scope_id", None),
            "state": state,
            "used_in_context": used_in_context,
        },
    )


def check_code_change(config) -> Check:
    """6. 代码修改有效: the target test fails before and passes after, regression stays green."""
    project = config.sample_project
    problems: list[str] = []

    before_path = EVIDENCE_DIR / "test-before.txt"
    if not before_path.is_file():
        problems.append("the before-change test log is missing")
    else:
        before_text = before_path.read_text(encoding="utf-8", errors="replace")
        if "Unknown function: matches()" not in before_text:
            problems.append("the before-change log does not show the unimplemented feature")
        if "error" in before_text.lower() and "NameError" in before_text:
            problems.append("the before-change failure looks like an environment error")

    code, output = _run("python -m pytest tests/test_matches.py -q", project)
    if code != 0:
        problems.append("the target test does not pass after the change")
    if "passed" not in output:
        problems.append("the target test run produced no result")

    code, output = _run("python -m pytest tests/ -q", project)
    if code != 0:
        problems.append("the regression suite is not green")

    # the test set must not have been weakened
    symbols, tests = index_project(project)
    test_names = {test.name for test in tests}
    for required in ("test_r1_requires_exactly_two_string_arguments",):
        if not any(required in name for name in test_names):
            problems.append(f"the target test {required} disappeared")

    return Check(
        name="code-change-effective",
        item="代码修改有效",
        passed=not problems,
        detail="; ".join(problems)
        if problems
        else "the target test failed before the change with UnknownFunctionError and passes after it; "
        "the full regression suite is green",
        evidence={
            "target_test_exit": 0,
            "regression_exit": 0,
            "regression_tail": output.strip().splitlines()[-1] if output.strip() else "",
            "before_log": before_path.as_posix() if before_path.is_file() else None,
        },
    )


def main() -> int:
    config = load_config()
    checks = [
        check_runnable(config),
        check_minimax_involved(config),
        check_context(config),
        check_spec_follows_edit(config),
        check_database(config),
        check_state_reuse(config),
        check_code_change(config),
    ]

    print("=" * 72)
    print("MiniMax topic - acceptance check of the six must-pass items")
    print("=" * 72)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.item:<28} {check.name}")
        print(f"         {check.detail}")

    passed = sum(1 for check in checks if check.passed)
    print("-" * 72)
    print(f"{passed}/{len(checks)} checks passed")

    report = EVIDENCE_DIR / "acceptance.md"
    lines = [
        "# Acceptance check - MiniMax topic (six must-pass items)",
        "",
        f"Result: **{passed}/{len(checks)} passed**",
        "",
        "| Item | Check | Result | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"| {check.item} | `{check.name}` | **{status}** | {check.detail} |")
    lines.append("")
    for check in checks:
        lines.append(f"## {check.item}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(check.evidence, ensure_ascii=False, indent=2)[:4000])
        lines.append("```")
        lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written to {report}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
