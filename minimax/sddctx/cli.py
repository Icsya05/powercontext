"""Command line entry point of the SDD context module.

    python -m sddctx doctor
    python -m sddctx import
    python -m sddctx context --task T-2026-001
    python -m sddctx patch   --task T-2026-001
    python -m sddctx test    --task T-2026-001
    python -m sddctx state   --task T-2026-001
    python -m sddctx run     --task T-2026-001

Run it from the ``minimax`` directory, or use ``python minimax/sddctx/cli.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # allow `python minimax/sddctx/cli.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sddctx.config import EVIDENCE_DIR, REPO_ROOT, load_config
from sddctx.evidence import EvidenceRecorder
from sddctx.powercontext_client import PowerContextClient
from sddctx.runner import (
    build_task_context,
    import_material,
    load_task,
    record_outcome,
    request_patch,
    request_test_file,
    apply_patch,
    revert_to_before_snapshot,
    run_acceptance,
    run_full_pipeline,
    save_state,
    write_test_file,
)
from sddctx.seekdb_store import DatabaseUnavailable, SeekDBStore


def _print(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _context_report(context) -> str:
    task = context.task
    lines = [
        f"Task      : {task.task_id}  {task.title}",
        f"Goal      : {task.goal}",
        f"Retrieval : keyword={context.retrieval.get('keyword')!r} "
        f"specs={context.retrieval.get('spec_hits')} "
        f"code={context.retrieval.get('code_hits')} "
        f"tests={context.retrieval.get('test_hits')} "
        f"(modes: spec={context.retrieval.get('spec_mode')}, "
        f"code={context.retrieval.get('code_mode')}, "
        f"test={context.retrieval.get('test_mode')})",
        "",
        "-- applicable specification entries --",
    ]
    for entry in context.specs:
        lines.append(f"  [{entry.kind}] {entry.identifier}  {entry.title}")
        lines.append(f"      source: {entry.source}")
    lines.append("")
    lines.append("-- code to change --")
    for entry in context.code:
        lines.append(f"  {entry.detail.get('file_path')} :: {entry.identifier}  ({entry.kind})")
        lines.append(f"      source: {entry.source}")
    lines.append("")
    lines.append("-- tests that verify the behaviour --")
    for entry in context.tests:
        lines.append(f"  {entry.identifier}")
        lines.append(f"      source: {entry.source}")
        if entry.detail.get("target"):
            lines.append(f"      verifies: {entry.detail['target']}")
    lines.append("")
    lines.append("-- progress recorded by earlier runs --")
    for item in context.finished:
        lines.append(f"  done: {item}")
    for item in context.verification:
        lines.append(f"  verified: {item}")
    for item in context.todo:
        lines.append(f"  todo: {item}")
    if not (context.finished or context.verification or context.todo):
        lines.append("  (nothing recorded yet)")
    return "\n".join(lines)


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder("doctor")
    ok = True

    store = SeekDBStore(config.seekdb, recorder=recorder)
    try:
        store.ensure_database()
        store.ensure_schema()
        counts = store.counts()
        _print("seekdb", {"status": "ok", **counts})
    except DatabaseUnavailable as exc:
        ok = False
        _print("seekdb", {"status": "unavailable", "detail": str(exc)})

    client = PowerContextClient(config.powercontext, recorder=recorder)
    try:
        health = client.health()
        _print("PowerContext", {"status": health.get("status"), "checks": health.get("checks")})
        if health.get("status") != "ready":
            ok = False
    except Exception as exc:  # noqa: BLE001
        ok = False
        _print("PowerContext", {"status": "unavailable", "detail": str(exc)})

    try:
        from sddctx.minmax_client import MiniMaxClient

        result = MiniMaxClient(config.minimax, recorder=recorder).complete(
            "Reply with exactly: OK", "ping", max_tokens=16, temperature=0.0
        )
        _print("MiniMax", {"status": "ok", "model": result.model, "reply": result.content[:120]})
    except Exception as exc:  # noqa: BLE001
        ok = False
        _print("MiniMax", {"status": "unavailable", "detail": str(exc)})

    _print("result", "all three technologies reachable" if ok else "at least one dependency is not ready")
    return 0 if ok else 1


def cmd_import(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder("import")
    report = import_material(config, recorder)
    _print("import", {"specs": report.specs, "code": report.code, "tests": report.tests, "stored": report.counts})
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"context-{args.task}")
    task = load_task(args.task, config)
    context = build_task_context(config, task, recorder)
    if args.json:
        _print("context", context.to_dict())
    else:
        _print("context", _context_report(context))
    if args.out:
        Path(args.out).write_text(
            json.dumps(context.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _print("written", args.out)
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"patch-{args.task}")
    task = load_task(args.task, config)
    feedback = ""
    if args.feedback_file:
        feedback = Path(args.feedback_file).read_text(encoding="utf-8", errors="replace")
    if args.revert:
        _print("revert", revert_to_before_snapshot(config, recorder))
        # Re-import, so the index in seekdb matches the restored files.  Without
        # this the context would still carry the previous attempt's code and
        # the model would produce a diff against the wrong baseline.
        _print("reimport", import_material(config, recorder).counts)
    context = build_task_context(config, task, recorder)
    patch = request_patch(config, task, context, recorder, feedback=feedback)
    if args.dry_run:
        _print("patch", patch)
        return 0
    result = apply_patch(config, patch, recorder)
    _print("patch", result)
    return 0 if result["exit_code"] == 0 else 1


def cmd_test(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"test-{args.task}")
    task = load_task(args.task, config)
    runs = run_acceptance(config, task, recorder)
    _print("tests", [run.to_dict() for run in runs])
    return 0 if all(run.passed for run in runs) else 1


def cmd_state(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"state-{args.task}")
    task = load_task(args.task, config)
    client = PowerContextClient(config.powercontext, recorder=recorder)
    scope = client.ensure_scope(task.task_id, f"sdd task {task.task_id}", task.title)
    state = client.load_state(scope.scope_id, task.task_id)
    _print("state", {"scope_id": scope.scope_id, "state": state})
    return 0 if state else 1


def cmd_testgen(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"testgen-{args.task}")
    task = load_task(args.task, config)
    feedback = ""
    if args.feedback_file:
        feedback = Path(args.feedback_file).read_text(encoding="utf-8", errors="replace")
    context = build_task_context(config, task, recorder)
    results = []
    for target in task.target_tests:
        path = config.sample_project / target
        if path.exists() and not args.force:
            results.append({"target": target, "status": "skipped (already exists)"})
            continue
        content = request_test_file(
            config, task, context, recorder, target, feedback=feedback
        )
        results.append({"target": target, **write_test_file(config, target, content, recorder)})
    _print("testgen", results)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    recorder = EvidenceRecorder(f"run-{args.task}")
    task = load_task(args.task, config)
    result = run_full_pipeline(config, task, recorder)
    _print("pipeline", result)
    report = EVIDENCE_DIR / f"run-{args.task}.md"
    recorder.write_markdown(report, f"Run evidence - {args.task}")
    _print("evidence", report.as_posix())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="SDD context module")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check seekdb, PowerContext and MiniMax").set_defaults(func=cmd_doctor)
    sub.add_parser("import", help="import specs, code and tests into seekdb").set_defaults(func=cmd_import)

    context_parser = sub.add_parser("context", help="assemble the development context")
    context_parser.add_argument("--task", required=True)
    context_parser.add_argument("--json", action="store_true")
    context_parser.add_argument("--out", help="write the context as JSON to this file")
    context_parser.set_defaults(func=cmd_context)

    patch_parser = sub.add_parser("patch", help="ask MiniMax for a patch and apply it")
    patch_parser.add_argument("--task", required=True)
    patch_parser.add_argument("--dry-run", action="store_true", help="print the patch, do not apply it")
    patch_parser.add_argument(
        "--feedback-file",
        help="file with the failure output of a previous attempt; MiniMax receives it",
    )
    patch_parser.add_argument(
        "--revert",
        action="store_true",
        help="restore the files under change from the before snapshot first",
    )
    patch_parser.set_defaults(func=cmd_patch)

    test_parser = sub.add_parser("test", help="run the acceptance commands")
    test_parser.add_argument("--task", required=True)
    test_parser.set_defaults(func=cmd_test)

    testgen_parser = sub.add_parser("testgen", help="ask MiniMax to write the target test file")
    testgen_parser.add_argument("--task", required=True)
    testgen_parser.add_argument("--force", action="store_true", help="overwrite an existing file")
    testgen_parser.add_argument(
        "--feedback-file",
        help="file with the failure output of a previous test file; MiniMax receives it",
    )
    testgen_parser.set_defaults(func=cmd_testgen)

    state_parser = sub.add_parser("state", help="read the task state back from PowerContext")
    state_parser.add_argument("--task", required=True)
    state_parser.set_defaults(func=cmd_state)

    run_parser = sub.add_parser("run", help="import -> context -> patch -> test -> save state")
    run_parser.add_argument("--task", required=True)
    run_parser.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
