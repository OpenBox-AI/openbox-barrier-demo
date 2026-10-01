"""Launch the local API and Sites dashboard with one command."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time

from dotenv import load_dotenv

from .run_manager import PROJECT_ROOT


def _port(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if not 1024 <= value <= 65535:
        raise ValueError(f"{name} must be between 1024 and 65535")
    return value


def _available_port(name: str, default: int) -> int:
    """Honor an explicit port, or choose the first free local default."""

    if name in os.environ:
        return _port(name, default)
    for candidate in range(default, min(default + 20, 65536)):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
        return candidate
    raise RuntimeError(f"No available localhost port found near {default}")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run() -> None:
    """Start both local processes and stop them together on Ctrl+C."""

    load_dotenv(PROJECT_ROOT / ".env")
    web_root = PROJECT_ROOT / "web"
    if not (web_root / "node_modules").is_dir():
        raise SystemExit("Frontend dependencies are missing. Run: cd web && npm install")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm is required to run the web dashboard")

    api_port = _available_port("DEMO_API_PORT", 8000)
    ui_port = _available_port("DEMO_UI_PORT", 3000)
    environment = os.environ.copy()
    environment.setdefault("NEXT_PUBLIC_API_BASE_URL", f"http://localhost:{api_port}")
    environment.setdefault("PYTHONUNBUFFERED", "1")

    api_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "openbox_langgraph_client_intelligence.web_api:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
    ]
    ui_command = [npm, "run", "dev", "--", "--port", str(ui_port)]

    print(f"Control room: http://localhost:{ui_port}")
    print(f"Local API:    http://127.0.0.1:{api_port}/api/health")
    print("Press Ctrl+C to stop both processes.\n")

    processes = [
        subprocess.Popen(api_command, cwd=PROJECT_ROOT, env=environment),
        subprocess.Popen(ui_command, cwd=web_root, env=environment),
    ]
    exit_code = 0
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        exit_code = max((process.returncode or 0) for process in processes)
    except KeyboardInterrupt:
        pass
    finally:
        for process in reversed(processes):
            _stop(process)
    raise SystemExit(exit_code)
