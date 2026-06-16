from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlmodel import Session

from apps.api.core.config import get_settings
from apps.api.db.session import engine, init_db
from apps.api.modules.background.jobs import run_runtime_job_cycle
from apps.api.modules.background.status import write_runtime_jobs_status
from apps.api.shared.structured_logging import configure_service_logging, log_event


logger = logging.getLogger("workbuddy.runtime_jobs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run WorkBuddy runtime background jobs.")
    parser.add_argument("--check", action="store_true", help="Validate runtime background job configuration and exit.")
    parser.add_argument("--once", action="store_true", help="Run a single scan cycle and exit.")
    return parser.parse_args()


def main() -> int:
    configure_service_logging("runtime-jobs")
    args = parse_args()
    settings = get_settings()
    if args.check:
        validate_settings(settings)
        log_event(logger, "runtime_jobs_check", status="ok")
        return 0

    init_db()
    validate_settings(settings)
    write_runtime_jobs_status(
        "starting",
        queue_driver=settings.background_queue_driver,
        interval_seconds=settings.background_jobs_interval_seconds,
    )
    log_event(logger, "runtime_jobs_start", queue_driver=settings.background_queue_driver)
    while True:
        try:
            with Session(engine) as session:
                summary = run_runtime_job_cycle(session)
            write_runtime_jobs_status(
                "running",
                heartbeat=True,
                queue_driver=settings.background_queue_driver,
                interval_seconds=settings.background_jobs_interval_seconds,
                append_cycle=summary,
            )
            log_event(logger, "runtime_jobs_cycle_completed", summary=summary)
        except Exception as exc:  # noqa: BLE001 - worker must report and continue
            logger.exception("Runtime jobs cycle failed")
            log_event(logger, "runtime_jobs_cycle_failed", error=str(exc))
            write_runtime_jobs_status(
                "failed",
                heartbeat=True,
                queue_driver=settings.background_queue_driver,
                interval_seconds=settings.background_jobs_interval_seconds,
                error=str(exc),
                append_error={"occurred_at": time_now_iso(), "error": str(exc)},
            )
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(max(5, settings.background_jobs_interval_seconds))


def validate_settings(settings) -> None:
    if not settings.enable_background_jobs:
        raise RuntimeError("Set ENABLE_BACKGROUND_JOBS=true before starting the runtime jobs worker.")
    if settings.background_jobs_interval_seconds < 5:
        raise RuntimeError("BACKGROUND_JOBS_INTERVAL_SECONDS must be at least 5 seconds.")


def time_now_iso() -> str:
    from apps.api.models import utc_now

    return utc_now().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
