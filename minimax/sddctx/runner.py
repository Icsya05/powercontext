"""The SDD context module pipeline.

``import`` -> ``context`` -> ``patch`` -> ``test`` -> ``state``

Each step records what it did, and the task state survives a module restart
because it lives in PowerContext.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .code_index import index_project
from .config import (
    BEFORE_SNAPSHOT_DIR,
    Config,
    EVIDENCE_DIR,
    REPO_ROOT,
    SPECS_DIR,
    TASKS_DIR,
    load_config,
)
from .context import DevelopmentContext, Task, build_context, parse_task
from .documents import load_documents
from .evidence import EvidenceRecorder
from .minmax_client import MiniMaxClient
from .powercontext_client import PowerContextClient
from .seekdb_store import SeekDBStore

PATCH_DIR = EVIDENCE_DIR / "patches"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_task(task_id: str, config: Config) -> Task:
    """Load one task document from ``minimax/tasks``."""
    documents = load_documents(TASKS_DIR)
    for document in documents:
        if document.doc_id == task_id or document.front_matter.get("task_id") == task_id:
            return parse_task(document)
    available = ", ".join(sorted({d.doc_id for d in documents})) or "(none)"
    raise SystemExit(f"unknown task {task_id!r}; available: {available}")


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ----------------------------------------------------------------------
# step 1: import material into seekdb
# ----------------------------------------------------------------------
@dataclass
class ImportReport:
    specs: int
    code: int
    tests: int
    counts: dict[str, int]


def import_material(config: Config, recorder: EvidenceRecorder) -> ImportReport:
    """Import specifications, code symbols and tests into seekdb."""
    store = SeekDBStore(config.seekdb, recorder=recorder)
    store.ensure_database()
    schema = store.ensure_schema()
    recorder.record("seekdb.schema", **schema)

    spec_count = 0
    for document in load_documents(SPECS_DIR):
        # Re-importing a document replaces its rows, so an edited
        # specification really replaces the old content.
        store.delete_source(document.source_path)
        for section in document.sections:
            store.upsert_spec(
                {
                    "spec_id": document.doc_id,
                    "section_id": section.section_id,
                    "kind": section.kind,
                    "title": section.title,
                    "content": f"{section.title}\n{section.body}",
                    "source_path": section.source_path,
                    "source_line": section.source_line,
                    "doc_title": document.title,
                }
            )
            spec_count += 1

    symbols, tests = index_project(config.sample_project)
    for symbol in symbols:
        store.upsert_code(
            {
                "file_path": symbol.file_path,
                "symbol": symbol.symbol,
                "kind": symbol.kind,
                "signature": symbol.signature,
                "content": symbol.content,
                "source_path": symbol.source_path,
                "source_line": symbol.source_line,
            }
        )
    for test in tests:
        store.upsert_test(
            {
                "test_id": test.test_id,
                "file_path": test.file_path,
                "name": test.name,
                "target": test.target,
                "content": test.content,
                "source_path": test.source_path,
                "source_line": test.source_line,
            }
        )

    counts = store.counts()
    recorder.record(
        "import.summary",
        specs_imported=spec_count,
        code_imported=len(symbols),
        tests_imported=len(tests),
        stored=counts,
    )
    return ImportReport(specs=spec_count, code=len(symbols), tests=len(tests), counts=counts)


# ----------------------------------------------------------------------
# step 2: build the context
# ----------------------------------------------------------------------
def build_task_context(
    config: Config,
    task: Task,
    recorder: EvidenceRecorder,
    pc_client: PowerContextClient | None = None,
) -> DevelopmentContext:
    store = SeekDBStore(config.seekdb, recorder=recorder)
    state = None
    if pc_client is not None:
        scope = pc_client.ensure_scope(task.task_id, f"sdd task {task.task_id}", f"SDD development task {task.task_id}")
        state = pc_client.load_state(scope.scope_id, task.task_id)
        if state:
            recorder.record("state.loaded", scope_id=scope.scope_id, state=state)
    context = build_context(task, store, state=state, project_root=config.sample_project)
    recorder.record(
        "context.built",
        task_id=task.task_id,
        retrieval=context.retrieval,
        specs=[entry.identifier for entry in context.specs],
        code=[f"{entry.detail.get('file_path')}::{entry.identifier}" for entry in context.code],
        tests=[entry.identifier for entry in context.tests],
    )
    return context


# ----------------------------------------------------------------------
# step 3: ask MiniMax for the patch
# ----------------------------------------------------------------------
SYSTEM_PROMPT = """You are a careful software engineer working on an existing Python project.
You are given the task, the specification entries that apply, the code that has to
change, and the tests that verify the behaviour.

Rules:
- Change only what the specification asks for.
- Do not change the behaviour that the specification lists as "must NOT change".
- Keep the existing code style, the existing import style and the existing error
  message conventions.
- Answer with exactly one fenced block that contains a unified diff.

The unified diff must use these repository-root relative paths:
{diff_paths}

The unified diff must start with `diff --git a/<path> b/<path>` and contain
`--- a/<path>` / `+++ b/<path>` headers with correct hunk line numbers.
"""


def request_patch(
    config: Config,
    task: Task,
    context: DevelopmentContext,
    recorder: EvidenceRecorder,
    attempt: int = 1,
    feedback: str = "",
) -> str:
    """Ask MiniMax for the patch that implements the task.

    ``feedback`` carries the failure output of a previous attempt, so the
    model can correct its own implementation instead of starting over.
    """
    client = MiniMaxClient(config.minimax, recorder=recorder)
    diff_paths = "\n".join(
        f"- {_repo_relative(config.sample_project / path)}"
        for path in task.applies_to
    )
    system = SYSTEM_PROMPT.format(diff_paths=diff_paths)
    user = context.to_prompt()
    user += (
        "\n\n## What to answer\n"
        "Return the unified diff that implements the task described above.\n"
        "Do not explain the change outside the diff block.\n"
    )
    if feedback.strip():
        user += (
            "\n\n## The previous attempt did not pass the tests\n"
            "Your earlier diff was applied and the acceptance tests failed with the "
            "output below.  Produce a corrected diff that fixes these failures.  "
            "Do not repeat the mistake.\n\n"
            "```\n" + feedback.strip()[-12000:] + "\n```\n"
        )
    result = client.complete(system, user)
    recorder.record(
        "patch.requested",
        attempt=attempt,
        model=result.model,
        request_id=result.request_id,
        usage=result.usage,
        patch_bytes=len(result.patch),
        feedback_chars=len(feedback),
    )
    return result.patch


def revert_to_before_snapshot(config: Config, recorder: EvidenceRecorder) -> dict[str, Any]:
    """Restore the files under change from the pre-change snapshot."""
    before_root = BEFORE_SNAPSHOT_DIR
    restored: list[str] = []
    if not before_root.is_dir():
        return {"restored": restored, "note": "no before snapshot found"}
    for path in sorted(before_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(before_root)
        target = config.sample_project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        restored.append(_repo_relative(target))
    result = {"restored": restored}
    recorder.record("patch.reverted", **result)
    return result


def apply_patch(config: Config, patch: str, recorder: EvidenceRecorder) -> dict[str, Any]:
    """Apply a unified diff to the working tree with ``git apply``.

    ``--recount`` is used because a model generated diff sometimes declares
    the wrong number of lines in a hunk header.  With ``--recount`` git
    recomputes the counts from the hunk body instead of rejecting the patch
    as corrupt.  The plain call is kept as a fallback.
    """
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    patch_path = PATCH_DIR / f"{stamp}.patch"
    patch_path.write_text(patch, encoding="utf-8")

    attempts: list[dict[str, Any]] = []
    process = None
    for extra in (["--recount"], []):
        process = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *extra, str(patch_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        attempts.append(
            {
                "flags": extra,
                "exit_code": process.returncode,
                "stderr": process.stderr.strip()[:800],
            }
        )
        if process.returncode == 0:
            break

    result = {
        "patch_path": _repo_relative(patch_path),
        "exit_code": process.returncode,
        "stdout": process.stdout.strip()[:800],
        "stderr": process.stderr.strip()[:800],
        "attempts": attempts,
    }
    recorder.record("patch.applied", **result)
    return result


# ----------------------------------------------------------------------
# step 3b: ask MiniMax for the target test file
# ----------------------------------------------------------------------
TESTGEN_SYSTEM_PROMPT = """You are a careful test engineer working on an existing Python project.
You are given a specification and the test style of the project.  Write the
acceptance test file that the specification asks for.

Rules:
- The test file must be complete and runnable on its own.
- It must import only from the standard library and from the project itself.
- It must fail on the current code base because the specified behaviour is not
  implemented yet - and it must fail with a clear "unknown function" style
  error, not with a collection or import error.
- Cover every numbered requirement of the specification, one test per
  requirement where that makes sense.
- Use the project's existing test style.

Answer with exactly one fenced block that contains the complete file content.
Do not write anything outside the fence.
"""


def request_test_file(
    config: Config,
    task: Task,
    context: DevelopmentContext,
    recorder: EvidenceRecorder,
    target: str,
    attempt: int = 1,
    feedback: str = "",
) -> str:
    """Ask MiniMax to write the acceptance test file ``target``."""
    client = MiniMaxClient(config.minimax, recorder=recorder)
    system = TESTGEN_SYSTEM_PROMPT
    lines = [context.to_prompt(), ""]
    lines.append(f"## What to answer")
    lines.append(
        f"Write the complete content of the file `{target}` inside the project "
        f"`{config.sample_project.name}`."
    )
    lines.append(
        "The file must exercise every numbered requirement of the specification above."
    )
    if feedback.strip():
        lines.append("")
        lines.append("## The previous version of this test file is wrong")
        lines.append(
            "Your earlier file failed with the error below.  Produce a corrected "
            "complete file.  Do not weaken the test: keep every requirement "
            "covered, fix the escaping or the syntax instead."
        )
        lines.append("")
        lines.append("```")
        lines.append(feedback.strip()[-12000:])
        lines.append("```")
    result = client.complete(system, "\n".join(lines))
    recorder.record(
        "testgen.requested",
        attempt=attempt,
        target=target,
        model=result.model,
        request_id=result.request_id,
        usage=result.usage,
        file_bytes=len(result.content),
        feedback_chars=len(feedback),
    )
    return client.extract_file(result.content)


def write_test_file(
    config: Config,
    target: str,
    content: str,
    recorder: EvidenceRecorder,
) -> dict[str, Any]:
    """Write the generated test file into the sample project."""
    path = config.sample_project / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    result = {"path": _repo_relative(path), "bytes": len(content.encode("utf-8"))}
    recorder.record("testgen.written", **result)
    return result


# ----------------------------------------------------------------------
# step 4: run the acceptance commands
# ----------------------------------------------------------------------
@dataclass
class TestRun:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "stdout_tail": self.stdout[-4000:],
            "stderr_tail": self.stderr[-2000:],
        }


def run_acceptance(config: Config, task: Task, recorder: EvidenceRecorder) -> list[TestRun]:
    """Run every acceptance command of the task inside the sample project."""
    runs: list[TestRun] = []
    for command in task.acceptance:
        process = subprocess.run(
            command,
            shell=True,
            cwd=str(config.sample_project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        run = TestRun(
            command=command,
            exit_code=process.returncode,
            stdout=process.stdout or "",
            stderr=process.stderr or "",
        )
        runs.append(run)
        recorder.record("test.run", **run.to_dict())
    return runs


# ----------------------------------------------------------------------
# step 5: task state in PowerContext
# ----------------------------------------------------------------------
def save_state(
    config: Config,
    task: Task,
    state: dict[str, Any],
    recorder: EvidenceRecorder,
    pc_client: PowerContextClient | None = None,
) -> dict[str, Any]:
    """Persist the task state into PowerContext."""
    client = pc_client or PowerContextClient(config.powercontext, recorder=recorder)
    scope = client.ensure_scope(task.task_id, f"sdd task {task.task_id}", f"SDD development task {task.task_id}")
    payload = {"task_id": task.task_id, "updated_at": _now(), **state}
    receipt = client.remember_state(scope.scope_id, payload, reason=f"sddctx {state.get('step', 'update')}")
    recorder.record("state.saved", scope_id=scope.scope_id, state=payload, receipt=receipt)
    return payload


def record_outcome(
    config: Config,
    task: Task,
    summary: str,
    status: str,
    checks: list[dict[str, Any]],
    observations: list[str],
    remaining: list[str],
    recorder: EvidenceRecorder,
    pc_client: PowerContextClient | None = None,
    source_suffix: str = "step",
) -> dict[str, Any]:
    """Record one step outcome in PowerContext."""
    client = pc_client or PowerContextClient(config.powercontext, recorder=recorder)
    scope = client.ensure_scope(task.task_id, f"sdd task {task.task_id}", f"SDD development task {task.task_id}")
    outcome = {
        "schema": "powercontext.task-outcome.v1",
        "trust": "untrusted_observation",
        "objective": task.goal or task.title,
        "status": status,
        "summary": summary,
        "observations": [
            {"text": text, "basis": "declared", "evidence": []} for text in observations
        ],
        "checks": [
            {
                "name": check["name"],
                "status": check["status"],
                "details": check.get("details", ""),
                "basis": "declared",
                "evidence": [],
            }
            for check in checks
        ],
        "produced_artifacts": [],
        "remaining_work": remaining,
    }
    receipt = client.record_outcome(
        scope.scope_id, f"sddctx:{task.task_id}:outcome:{source_suffix}", outcome
    )
    recorder.record("outcome.recorded", scope_id=scope.scope_id, outcome=outcome, receipt=receipt)
    return receipt


# ----------------------------------------------------------------------
# the whole pipeline
# ----------------------------------------------------------------------
def run_full_pipeline(config: Config, task: Task, recorder: EvidenceRecorder) -> dict[str, Any]:
    """import -> context -> target test -> patch -> apply -> test -> save state.

    The target test is generated *before* the implementation, so the
    "fails before, passes after" evidence is produced by the same run.
    """
    pc_client = PowerContextClient(config.powercontext, recorder=recorder)

    report = import_material(config, recorder)
    recorder.record("pipeline.import", **report.counts, specs=report.specs, code=report.code, tests=report.tests)

    context = build_task_context(config, task, recorder, pc_client=pc_client)

    # --- phase 1: the acceptance test, written from the specification ----
    generated: list[dict[str, Any]] = []
    for target in task.target_tests:
        path = config.sample_project / target
        if path.exists():
            recorder.record("testgen.skipped", target=target, reason="file already exists")
            continue
        content = request_test_file(config, task, context, recorder, target)
        generated.append(write_test_file(config, target, content, recorder))

    # The target test must fail now, because the behaviour is not implemented.
    before: list[dict[str, Any]] = []
    if task.acceptance:
        before = [run.to_dict() for run in run_acceptance(config, task, recorder)]
        recorder.record(
            "pipeline.before",
            results=before,
            note="expected to fail: the specified behaviour is not implemented yet",
        )

    # Re-import so the freshly written test file is part of the index.
    if generated:
        import_material(config, recorder)

    context = build_task_context(config, task, recorder, pc_client=pc_client)

    # --- phase 2: the implementation -------------------------------------
    patch = request_patch(config, task, context, recorder)
    apply_result = apply_patch(config, patch, recorder)

    runs = run_acceptance(config, task, recorder)

    finished = list(context.finished)
    verification = list(context.verification)
    todo = list(context.todo)
    if generated:
        finished.append(f"MiniMax wrote the acceptance test {', '.join(task.target_tests)}")
    if apply_result["exit_code"] == 0:
        finished.append("MiniMax patch applied to the working tree")
    else:
        todo.append("apply the MiniMax patch (git apply failed)")
    for run in runs:
        status = "passed" if run.passed else "failed"
        verification.append(f"{run.command} -> exit {run.exit_code} ({status})")
        if run.passed:
            finished.append(f"{run.command} passed")
        else:
            todo.append(f"{run.command} still failing")

    state = {
        "step": "patched-and-tested",
        "finished": finished,
        "todo": todo,
        "verification": verification,
        "patch_applied": apply_result["exit_code"] == 0,
        "tests_passed": all(run.passed for run in runs),
    }
    save_state(config, task, state, recorder, pc_client=pc_client)
    record_outcome(
        config,
        task,
        summary="MiniMax produced the acceptance test and the implementation; acceptance commands were executed.",
        status="succeeded" if all(run.passed for run in runs) else "partial",
        checks=[
            {"name": run.command, "status": "passed" if run.passed else "failed", "details": f"exit {run.exit_code}"}
            for run in runs
        ],
        observations=[f"patch applied: {apply_result['exit_code'] == 0}"],
        remaining=todo,
        recorder=recorder,
        pc_client=pc_client,
        source_suffix="pipeline",
    )

    return {
        "import": report.counts,
        "generated_tests": generated,
        "before": before,
        "context": context.retrieval,
        "patch": apply_result,
        "tests": [run.to_dict() for run in runs],
        "state": state,
    }


def default_config() -> Config:
    return load_config()
