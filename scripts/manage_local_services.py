from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = ROOT / "apps/api/data/processes"
DEFAULT_LOG_DIR = ROOT / "apps/api/data/logs/services"
DEFAULT_SERVICES = ("api", "web", "runtime-jobs")


@dataclass(frozen=True)
class ServiceSpec:
    command: tuple[str, ...]
    env: dict[str, str]
    health_url: str | None = None
    status_path: Path | None = None


def service_specs() -> dict[str, ServiceSpec]:
    return {
        "api": ServiceSpec(
            command=(".venv/bin/uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"),
            env={"WORKBUDDY_ENABLE_BACKGROUND_JOBS": "true"},
            health_url="http://127.0.0.1:8000/health",
        ),
        "web": ServiceSpec(
            command=("npm", "--prefix", "apps/web", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"),
            env={},
            health_url="http://127.0.0.1:5173/",
        ),
        "runtime-jobs": ServiceSpec(
            command=(".venv/bin/python", "-m", "apps.api.workers.runtime_jobs"),
            env={"WORKBUDDY_ENABLE_BACKGROUND_JOBS": "true"},
            status_path=ROOT / "apps/api/data/runtime_jobs_status.json",
        ),
        "feishu-worker": ServiceSpec(
            command=(".venv/bin/python", "-m", "apps.api.workers.feishu_stream"),
            env={"WORKBUDDY_ENABLE_REAL_IM_ADAPTERS": "true"},
            status_path=ROOT / "apps/api/data/feishu_stream_status.json",
        ),
    }


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).resolve()
    log_dir = Path(args.log_dir).resolve()
    if args.command == "_supervise":
        spec = service_specs()[args.service]
        return supervise_command(args.service, list(spec.command), spec.env, state_dir, log_dir)

    services = expand_services(args.services)
    if args.command == "start":
        return start_services(services, state_dir, log_dir)
    if args.command == "stop":
        return stop_services(services, state_dir)
    if args.command == "restart":
        stop_services(services, state_dir)
        return start_services(services, state_dir, log_dir)
    if args.command == "status":
        return print_status(services, state_dir)
    if args.command == "logs":
        return print_logs(services, log_dir, args.lines)
    if args.command == "check":
        return check_manager(state_dir, log_dir)
    raise RuntimeError(f"Unsupported command: {args.command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage supervised WorkBuddy local services.")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "stop", "restart", "status"):
        target = subparsers.add_parser(command)
        target.add_argument("services", nargs="*", help="api, web, runtime-jobs, feishu-worker, core, or workers")
    logs = subparsers.add_parser("logs")
    logs.add_argument("services", nargs="*")
    logs.add_argument("--lines", type=int, default=30)
    check = subparsers.add_parser("check")
    check.set_defaults(services=[])
    supervise = subparsers.add_parser("_supervise", help=argparse.SUPPRESS)
    supervise.add_argument("service", choices=sorted(service_specs()))
    supervise.set_defaults(services=[])
    return parser.parse_args()


def expand_services(values: list[str]) -> list[str]:
    requested = values or ["core"]
    aliases = {
        "core": list(DEFAULT_SERVICES),
        "workers": ["runtime-jobs"],
    }
    expanded: list[str] = []
    available = service_specs()
    for value in requested:
        names = aliases.get(value, [value])
        for name in names:
            if name not in available:
                raise SystemExit(f"Unknown service: {name}")
            if name not in expanded:
                expanded.append(name)
    return expanded


def start_services(services: list[str], state_dir: Path, log_dir: Path) -> int:
    state_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    specs = service_specs()
    failures = 0
    for service in services:
        current = read_state(state_dir, service)
        if is_running(current.get("supervisor_pid")):
            print(f"[ok] {service}: already supervised (pid {current['supervisor_pid']})")
            continue
        supervisor_log = log_dir / f"{service}-supervisor.log"
        with supervisor_log.open("ab") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--state-dir",
                    str(state_dir),
                    "--log-dir",
                    str(log_dir),
                    "_supervise",
                    service,
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        write_state(state_dir, service, {"service": service, "state": "starting", "supervisor_pid": process.pid})
        def healthy() -> bool:
            child_pid = read_state(state_dir, service).get("child_pid")
            return service_health(specs[service], is_running(child_pid))["ok"]

        if wait_for(healthy, timeout=12):
            state = read_state(state_dir, service)
            print(f"[ok] {service}: started (supervisor {process.pid}, child {state.get('child_pid')})")
        else:
            failures += 1
            print(f"[fail] {service}: child did not start; inspect {supervisor_log}")
    return 1 if failures else 0


def stop_services(services: list[str], state_dir: Path) -> int:
    failures = 0
    for service in services:
        state = read_state(state_dir, service)
        supervisor_pid = state.get("supervisor_pid")
        if not is_running(supervisor_pid):
            print(f"[ok] {service}: already stopped")
            continue
        try:
            os.kill(int(supervisor_pid), signal.SIGTERM)
        except OSError as exc:
            failures += 1
            print(f"[fail] {service}: {exc}")
            continue
        if wait_for(lambda: not is_running(supervisor_pid), timeout=10):
            print(f"[ok] {service}: stopped")
        else:
            failures += 1
            print(f"[fail] {service}: supervisor {supervisor_pid} did not stop")
    return 1 if failures else 0


def print_status(services: list[str], state_dir: Path) -> int:
    failures = 0
    specs = service_specs()
    for service in services:
        state = read_state(state_dir, service)
        supervisor_running = is_running(state.get("supervisor_pid"))
        child_running = is_running(state.get("child_pid"))
        health = service_health(specs[service], child_running)
        ok = supervisor_running and child_running and health["ok"]
        print(
            f"[{'ok' if ok else 'warn'}] {service}: state={state.get('state', 'not_started')} "
            f"supervisor={state.get('supervisor_pid', '-')} child={state.get('child_pid', '-')} "
            f"restarts={state.get('restart_count', 0)} health={health['message']}"
        )
        if not ok:
            failures += 1
    return 1 if failures else 0


def print_logs(services: list[str], log_dir: Path, lines: int) -> int:
    found = False
    for service in services:
        path = log_dir / f"{service}.log"
        if not path.exists():
            print(f"[warn] {service}: no log at {path}")
            continue
        found = True
        print(f"== {service} ==")
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, lines):]:
            print(line)
    return 0 if found else 1


def check_manager(state_dir: Path, log_dir: Path) -> int:
    state_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    checks = [
        ("service_specs", set(service_specs()) == {"api", "web", "runtime-jobs", "feishu-worker"}),
        ("default_excludes_feishu", "feishu-worker" not in DEFAULT_SERVICES),
        ("state_dir", state_dir.is_dir() and os.access(state_dir, os.W_OK)),
        ("log_dir", log_dir.is_dir() and os.access(log_dir, os.W_OK)),
    ]
    for name, ok in checks:
        print(f"[{'ok' if ok else 'fail'}] {name}")
    return 0 if all(ok for _, ok in checks) else 1


def supervise_command(
    service: str,
    command: list[str],
    extra_env: dict[str, str],
    state_dir: Path,
    log_dir: Path,
) -> int:
    state_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    stopping = False
    child: subprocess.Popen[str] | None = None
    restart_count = 0
    restart_times: list[float] = []
    max_restarts = int(os.getenv("WORKBUDDY_SUPERVISOR_MAX_RESTARTS", "5"))
    restart_window = int(os.getenv("WORKBUDDY_SUPERVISOR_RESTART_WINDOW_SECONDS", "60"))
    restart_delay = float(os.getenv("WORKBUDDY_SUPERVISOR_RESTART_DELAY_SECONDS", "1"))
    max_log_bytes = int(os.getenv("WORKBUDDY_SERVICE_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    backup_count = int(os.getenv("WORKBUDDY_SERVICE_LOG_BACKUPS", "3"))
    writer = RotatingLogWriter(log_dir / f"{service}.log", max_log_bytes, backup_count)

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            terminate_process_group(child.pid)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    env = {**os.environ, **extra_env}
    while not stopping:
        now = time.time()
        restart_times = [value for value in restart_times if now - value <= restart_window]
        if len(restart_times) >= max_restarts:
            write_state(
                state_dir,
                service,
                {
                    "service": service,
                    "state": "failed",
                    "supervisor_pid": os.getpid(),
                    "child_pid": None,
                    "restart_count": restart_count,
                    "last_error": f"restart limit reached ({max_restarts}/{restart_window}s)",
                },
            )
            writer.write(f"[supervisor] restart limit reached ({max_restarts}/{restart_window}s)\n")
            return 1

        child = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        started_at = iso_now()
        write_state(
            state_dir,
            service,
            {
                "service": service,
                "state": "running",
                "supervisor_pid": os.getpid(),
                "child_pid": child.pid,
                "restart_count": restart_count,
                "started_at": started_at,
                "command": command,
                "log_path": str(writer.path),
            },
        )
        writer.write(f"[supervisor] started child {child.pid}: {' '.join(command)}\n")
        while child.poll() is None and not stopping:
            if child.stdout is not None:
                readable, _, _ = select.select([child.stdout], [], [], 1)
                if readable:
                    line = child.stdout.readline()
                    if line:
                        writer.write(line)
            update_state(state_dir, service, heartbeat_at=iso_now())

        if stopping:
            if child.poll() is None:
                terminate_process_group(child.pid)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                kill_process_group(child.pid)
            drain_output(child, writer)
            write_state(
                state_dir,
                service,
                {
                    **read_state(state_dir, service),
                    "state": "stopped",
                    "child_pid": None,
                    "stopped_at": iso_now(),
                },
            )
            writer.write("[supervisor] stopped\n")
            return 0

        exit_code = child.returncode
        drain_output(child, writer)
        restart_count += 1
        restart_times.append(time.time())
        writer.write(f"[supervisor] child exited with code {exit_code}; restarting\n")
        write_state(
            state_dir,
            service,
            {
                **read_state(state_dir, service),
                "state": "restarting",
                "child_pid": None,
                "restart_count": restart_count,
                "last_exit_code": exit_code,
                "last_exit_at": iso_now(),
            },
        )
        time.sleep(max(0.1, restart_delay))
    return 0


class RotatingLogWriter:
    def __init__(self, path: Path, max_bytes: int, backup_count: int) -> None:
        self.path = path
        self.max_bytes = max(1, max_bytes)
        self.backup_count = max(1, backup_count)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, text: str) -> None:
        encoded = text.encode("utf-8", errors="replace")
        if self.path.exists() and self.path.stat().st_size + len(encoded) > self.max_bytes:
            self.rotate()
        with self.path.open("ab") as output:
            output.write(encoded)

    def rotate(self) -> None:
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        if self.path.exists():
            self.path.replace(self.path.with_name(f"{self.path.name}.1"))


def service_health(spec: ServiceSpec, process_running: bool) -> dict[str, Any]:
    if not process_running:
        return {"ok": False, "message": "process stopped"}
    if spec.health_url:
        try:
            with urlopen(spec.health_url, timeout=1) as response:
                return {"ok": response.status < 500, "message": f"http {response.status}"}
        except (OSError, URLError) as exc:
            return {"ok": False, "message": f"http unavailable: {exc}"}
    if spec.status_path:
        try:
            payload = json.loads(spec.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "message": f"status unavailable: {exc}"}
        return {"ok": payload.get("status") == "running", "message": str(payload.get("status") or "unknown")}
    return {"ok": True, "message": "process running"}


def read_state(state_dir: Path, service: str) -> dict[str, Any]:
    path = state_dir / f"{service}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_dir: Path, service: str, payload: dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{service}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def update_state(state_dir: Path, service: str, **fields: Any) -> None:
    write_state(state_dir, service, {**read_state(state_dir, service), **fields})


def is_running(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return


def kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        return


def drain_output(process: subprocess.Popen[str], writer: RotatingLogWriter) -> None:
    if process.stdout is None:
        return
    remaining = process.stdout.read()
    if remaining:
        writer.write(remaining)


def wait_for(predicate, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return bool(predicate())


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
