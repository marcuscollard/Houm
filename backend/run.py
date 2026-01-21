import os

import uvicorn


def main() -> None:
    host = os.getenv("HOUM_HOST", "0.0.0.0")
    port = int(os.getenv("HOUM_PORT") or os.getenv("PORT", "8000"))
    uvicorn.run("backend.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
