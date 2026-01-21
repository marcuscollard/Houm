from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if not key or key in os.environ:
            continue
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


_env_file = os.getenv("ENV_FILE")
if _env_file:
    _load_env_file(Path(_env_file))
else:
    _load_env_file(BASE_DIR / ".env")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
