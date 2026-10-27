"""Install WSL 2 and Docker Desktop on Windows, then wait for the engine.

Written for this machine, where ``wsl --install`` fails with error 403
(it tries to pull the kernel from Windows Update).  The two Windows optional
features are enabled with DISM beforehand, and the WSL kernel is installed
from the official MSI, which ships the kernel and therefore does not need
Windows Update.

Usage (run after a reboot, from an elevated PowerShell):

    python dify/deploy/install_docker_windows.py
    python dify/deploy/install_docker_windows.py --check-only

Steps:
1. verify the WSL optional features are Enabled;
2. install the WSL MSI if ``wsl --version`` still does not work;
3. install Docker Desktop silently (``--quiet --accept-license``);
4. start Docker Desktop and wait until ``docker version`` reports a Server.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

WSL_MSI = Path(r"D:\Tools\wsl\wsl.3.0.4.0.x64.msi")
DOCKER_INSTALLER = Path(r"D:\Tools\docker\Docker Desktop Installer.exe")
DOCKER_DESKTOP = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
DOCKER_CLI = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")


def is_admin() -> bool:
    try:
        import ctypes

        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run(cmd: list[str], timeout: float = 1800.0) -> int:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(
        cmd, text=True, capture_output=True, timeout=timeout, errors="replace"
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def wsl_works() -> bool:
    try:
        result = subprocess.run(
            ["wsl.exe", "--version"],
            text=True,
            capture_output=True,
            timeout=30,
            errors="replace",
        )
    except Exception:
        return False
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and "WSL" in output.upper() and "version" in output.lower()


def docker_cli() -> str | None:
    for candidate in (DOCKER_CLI,):
        if candidate.exists():
            return str(candidate)
    found = shutil_which("docker")
    return found


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def docker_engine_ready() -> bool:
    cli = docker_cli()
    if not cli:
        return False
    try:
        result = subprocess.run(
            [cli, "version", "--format", "{{.Server.Version}}"],
            text=True,
            capture_output=True,
            timeout=30,
        )
    except Exception:
        return False
    return result.returncode == 0 and result.stdout.strip() != ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Install WSL2 and Docker Desktop on Windows.")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    args = parser.parse_args()

    print("=== current state ===")
    print(f"wsl --version works : {wsl_works()}")
    print(f"docker cli present  : {bool(docker_cli())}")
    print(f"docker engine ready : {docker_engine_ready()}")
    print(f"elevated            : {is_admin()}")

    if args.check_only:
        return 0

    if not is_admin():
        print("\nThis script needs an elevated PowerShell (run as administrator).")
        return 2

    if not wsl_works():
        print("\n=== installing the WSL kernel from the MSI ===")
        if not WSL_MSI.exists():
            print(f"MSI not found: {WSL_MSI}")
            return 2
        code = run(["msiexec.exe", "/i", str(WSL_MSI), "/quiet", "/norestart"])
        print(f"msiexec exit code: {code}")
        print("checking wsl --version ...")
        print(f"wsl --version works : {wsl_works()}")
        if not wsl_works():
            print(
                "WSL still not usable. Enable the two Windows features and reboot:\n"
                "  dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart\n"
                "  dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart"
            )

    if args.skip_docker:
        return 0

    if DOCKER_DESKTOP.exists():
        print("\n=== Docker Desktop already installed ===")
    else:
        print("\n=== installing Docker Desktop ===")
        if not DOCKER_INSTALLER.exists():
            print(f"installer not found: {DOCKER_INSTALLER}")
            return 2
        code = run(
            [
                str(DOCKER_INSTALLER),
                "install",
                "--quiet",
                "--accept-license",
                "--backend=wsl-2",
            ]
        )
        print(f"installer exit code: {code}")

    print("\n=== starting Docker Desktop ===")
    if DOCKER_DESKTOP.exists():
        subprocess.Popen([str(DOCKER_DESKTOP)], close_fds=True)

    print("waiting for the engine (up to 10 minutes) ...")
    deadline = time.time() + 600
    while time.time() < deadline:
        if docker_engine_ready():
            print("\nDocker engine is ready.")
            result = subprocess.run(
                [docker_cli(), "run", "--rm", "hello-world"],
                text=True,
                capture_output=True,
                timeout=300,
            )
            print(result.stdout.strip())
            return 0
        time.sleep(5)
    print("the engine did not become ready in time; check the Docker Desktop window.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
