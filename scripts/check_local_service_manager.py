from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.shared.structured_logging import JsonLineFileHandler
from scripts.manage_local_services import RotatingLogWriter, expand_services, is_running, read_state, service_specs


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="workbuddy-service-manager-") as temp_dir:
        temp_root = Path(temp_dir)
        state_dir = temp_root / "state"
        log_dir = temp_root / "logs"
        marker = temp_root / "started.txt"
        fixture = temp_root / "flaky_service.py"
        fixture.write_text(
            "from pathlib import Path\n"
            "import os\n"
            "import time\n"
            f"marker = Path({str(marker)!r})\n"
            "if not marker.exists():\n"
            "    marker.write_text('first', encoding='utf-8')\n"
            "    print('first run crashes', flush=True)\n"
            "    raise SystemExit(7)\n"
            "marker.write_text('restarted', encoding='utf-8')\n"
            "print('second run stays alive', flush=True)\n"
            "while True:\n"
            "    time.sleep(0.2)\n",
            encoding="utf-8",
        )

        writer = RotatingLogWriter(log_dir / "rotation.log", 32, 2)
        writer.write("a" * 24 + "\n")
        writer.write("b" * 24 + "\n")
        record(checks, "log_rotation", (log_dir / "rotation.log.1").exists(), "Oversized service logs rotate with backups.")
        structured_path = log_dir / "structured.jsonl"
        structured = JsonLineFileHandler(structured_path, "acceptance")
        structured.max_bytes = 80
        structured.emit(make_log_record("first structured event"))
        structured.emit(make_log_record("second structured event"))
        record(
            checks,
            "structured_log_rotation",
            (log_dir / "structured.jsonl.1").exists(),
            "Structured JSONL logs rotate before exceeding their size budget.",
        )
        record(checks, "safe_defaults", expand_services([]) == ["api", "web", "runtime-jobs"], "Default services exclude the real Feishu worker.")
        record(
            checks,
            "api_worker_alignment",
            service_specs()["api"].env.get("WORKBUDDY_ENABLE_BACKGROUND_JOBS") == "true",
            "Managed API health configuration matches the managed runtime-jobs worker.",
        )

        command = (
            "from pathlib import Path; "
            "from scripts.manage_local_services import supervise_command; "
            f"raise SystemExit(supervise_command('fixture', [{sys.executable!r}, {str(fixture)!r}], {{}}, "
            f"Path({str(state_dir)!r}), Path({str(log_dir)!r})))"
        )
        env = {
            **os.environ,
            "WORKBUDDY_SUPERVISOR_RESTART_DELAY_SECONDS": "0.1",
            "WORKBUDDY_SUPERVISOR_MAX_RESTARTS": "4",
        }
        supervisor = subprocess.Popen(
            [sys.executable, "-c", command],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            restarted = wait_for(lambda: marker.exists() and marker.read_text(encoding="utf-8") == "restarted", 8)
            state = read_state(state_dir, "fixture")
            record(
                checks,
                "crash_restart",
                restarted and state.get("restart_count", 0) >= 1 and is_running(state.get("child_pid")),
                "A crashed child restarts and the replacement remains alive.",
            )
            record(
                checks,
                "state_tracking",
                state.get("supervisor_pid") == supervisor.pid and state.get("state") == "running",
                "Supervisor and child PIDs are written to isolated state.",
            )
            service_log = (log_dir / "fixture.log").read_text(encoding="utf-8")
            record(
                checks,
                "combined_logs",
                "first run crashes" in service_log and "second run stays alive" in service_log,
                "Child output from both attempts is retained.",
            )
        finally:
            if supervisor.poll() is None:
                os.kill(supervisor.pid, signal.SIGTERM)
                try:
                    supervisor.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(supervisor.pid, signal.SIGKILL)
                    supervisor.wait(timeout=5)
        stopped_state = read_state(state_dir, "fixture")
        record(
            checks,
            "graceful_stop",
            supervisor.returncode == 0 and stopped_state.get("state") == "stopped",
            "Stopping the supervisor terminates its child and records a stopped state.",
        )
        record(
            checks,
            "temporary_artifacts",
            str(state_dir).startswith(temp_dir) and str(log_dir).startswith(temp_dir),
            "Acceptance state and logs stay inside the temporary directory.",
        )

    for name, ok, message in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}: {message}")
    failed = [item for item in checks if not item[1]]
    if failed:
        print(f"\n{len(failed)} local service manager check(s) failed.", file=sys.stderr)
        return 1
    print(f"\nLocal service manager checks passed ({len(checks)} checks).")
    return 0


def wait_for(predicate, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


def record(checks: list[tuple[str, bool, str]], name: str, ok: bool, message: str) -> None:
    checks.append((name, bool(ok), message))


def make_log_record(message: str):
    import logging

    return logging.LogRecord("acceptance", logging.INFO, __file__, 1, message, (), None)


if __name__ == "__main__":
    raise SystemExit(main())
