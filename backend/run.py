import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    host = os.getenv("HOUM_HOST", "0.0.0.0")
    port = int(os.getenv("HOUM_PORT") or os.getenv("PORT", "8000"))
    uvicorn.run("backend.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
