from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    print("Alembic upgrade head completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
