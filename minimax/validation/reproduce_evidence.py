"""Rebuild the before/after evidence for the development task.

The script is the reproducible version of what happened during development:

1. restore the files under change from the pre-change snapshot,
2. run the acceptance commands - they must fail because the specified
   behaviour is not implemented yet,
3. apply the MiniMax patch,
4. run the acceptance commands again - they must all pass,
5. re-import the material so the index matches the delivered code,
6. store the task state in PowerContext.

Every step writes into ``minimax/evidence/``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sddctx.config import EVIDENCE_DIR, REPO_ROOT, load_config  # noqa: E402
from sddctx.evidence import EvidenceRecorder  # noqa: E402
from sddctx.powercontext_client import PowerContextClient  # noqa: E402
from sddctx.runner import (  # noqa: E402
    apply_patch,
    import_material,
    load_task,
    record_outcome,
    revert_to_before_snapshot,
    run_acceptance,
    save_state,
)

PATCHES = EVIDENCE_DIR / "patches"
TASK_ID = "T-2026-001"


def run(command: str, cwd: Path) -> tuple[int, str]:
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


def apply_patch_file(patch_path: Path) -> tuple[int, str]:
    for extra in (["--recount"], []):
        process = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *extra, str(patch_path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if process.returncode == 0:
            return process.returncode, process.stderr.strip()
    return process.returncode, process.stderr.strip()


def write_log(path: Path, title: str, command: str, exit_code: int, output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# {title}\n"
        f"# command: {command}\n"
        f"# cwd: minimax/sample_project/jmespath\n"
        f"# exit code: {exit_code}\n"
        f"# generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
    )
    path.write_text(header + output, encoding="utf-8")
    print(f"  wrote {path.name} (exit={exit_code})")


def log_name(prefix: str, command: str) -> str:
    """A stable file name for one acceptance command."""
    slug = command.replace("python -m pytest ", "").replace(" ", "_").replace("/", "-")
    return f"{prefix}-{slug}.txt"


def main() -> int:
    config = load_config()
    recorder = EvidenceRecorder("reproduce")
    task = load_task(TASK_ID, config)
    project = config.sample_project
    evidence = EVIDENCE_DIR

    print("[1] restore the pre-change snapshot")
    revert_to_before_snapshot(config, recorder)

    print("[2] run the acceptance commands BEFORE the change (they must fail)")
    before_runs = run_acceptance(config, task, recorder)
    for run_result in before_runs:
        write_log(
            evidence / log_name("test-before", run_result.command),
            "Target test run BEFORE the implementation",
            run_result.command,
            run_result.exit_code,
            run_result.stdout + run_result.stderr,
        )
    if any(r.passed for r in before_runs):
        print("  ERROR: a command passed before the change; the evidence is not valid")
        return 1

    print("[3] apply the MiniMax patch")
    patches = sorted(PATCHES.glob("*.patch"))
    if not patches:
        print("  ERROR: no patch file found")
        return 1
    # the last patch is the one that applies cleanly
    chosen = None
    for candidate in reversed(patches):
        result = apply_patch(
            config,
            candidate.read_text(encoding="utf-8", errors="replace"),
            recorder,
            patch_path=candidate,
        )
        if result["exit_code"] == 0:
            chosen = candidate
            print(f"  applied {candidate.name}")
            break
        print(f"  {candidate.name} does not apply: {result['stderr'].splitlines()[-1] if result['stderr'] else ''}")
    if chosen is None:
        print("  ERROR: no patch applies")
        return 1
    recorder.record("evidence.patch_applied", patch=chosen.name)

    print("[4] run the acceptance commands AFTER the change (they must pass)")
    after_runs = run_acceptance(config, task, recorder)
    for run_result in after_runs:
        write_log(
            evidence / log_name("test-after", run_result.command),
            "Acceptance run AFTER the implementation",
            run_result.command,
            run_result.exit_code,
            run_result.stdout + run_result.stderr,
        )
    if not all(r.passed for r in after_runs):
        print("  ERROR: a command still fails after the change")
        return 1

    print("[5] re-import the material so the index matches the delivered code")
    report = import_material(config, recorder)
    print("  ", report.counts)

    print("[6] store the task state in PowerContext")
    client = PowerContextClient(config.powercontext, recorder=recorder)
    finished = [
        f"MiniMax wrote the acceptance test {', '.join(task.target_tests)}",
        "MiniMax patch applied to the working tree",
    ]
    finished += [f"{r.command} passed" for r in after_runs]
    verification = [f"{r.command} -> exit {r.exit_code} (passed)" for r in after_runs]
    verification += [f"{r.command} -> exit {r.exit_code} (failed, feature not implemented)" for r in before_runs]
    state = {
        "step": "patched-and-tested",
        "finished": finished,
        "todo": [],
        "verification": verification,
        "patch_applied": True,
        "tests_passed": True,
    }
    save_state(config, task, state, recorder, pc_client=client)
    record_outcome(
        config,
        task,
        summary="MiniMax wrote the acceptance test and the implementation; both acceptance commands are green.",
        status="succeeded",
        checks=[
            {"name": r.command, "status": "passed", "details": f"exit {r.exit_code}"}
            for r in after_runs
        ],
        observations=[f"patch applied: {chosen.name}"],
        remaining=[],
        recorder=recorder,
        pc_client=client,
        source_suffix="reproduce",
    )

    summary = {
        "patch": chosen.name,
        "before": [r.to_dict() for r in before_runs],
        "after": [r.to_dict() for r in after_runs],
        "state": state,
    }
    (evidence / "reproduce-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    recorder.write_markdown(evidence / "reproduce.md", "Reproduction evidence")
    print("[done] evidence written to", evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
