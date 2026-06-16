from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = ROOT / "apps" / "api" / "data" / "logs"


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir or DEFAULT_LOG_DIR)
    if args.command == "status":
        return print_status(log_dir)
    if args.command == "tail":
        return print_tail(log_dir, args.lines)
    raise SystemExit(f"Unknown command: {args.command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect WorkBuddy structured runtime logs.")
    parser.add_argument("--log-dir", default="", help="Log directory. Defaults to apps/api/data/logs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Check whether structured logs are available.")
    tail = subparsers.add_parser("tail", help="Print recent structured log events.")
    tail.add_argument("--lines", type=int, default=20, help="Maximum lines per log file.")
    return parser.parse_args()


def print_status(log_dir: Path) -> int:
    files = sorted(log_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True) if log_dir.exists() else []
    print(f"Log directory: {log_dir}")
    if not log_dir.exists():
        print("[warn] log directory does not exist yet")
        return 1
    if not files:
        print("[warn] no structured log files found")
        return 1
    for file in files:
        print(f"[ok] {file.name}: {file.stat().st_size} bytes")
    return 0


def print_tail(log_dir: Path, lines: int) -> int:
    files = sorted(log_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True) if log_dir.exists() else []
    if not files:
        print("No structured logs found.")
        return 1
    for file in files:
        print(f"== {file.name} ==")
        for line in file.read_text(encoding="utf-8").splitlines()[-lines:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(line)
                continue
            print(
                f"{event.get('ts')} {event.get('level')} {event.get('service')} "
                f"{event.get('event')} {json.dumps(event.get('fields') or {}, ensure_ascii=False)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
