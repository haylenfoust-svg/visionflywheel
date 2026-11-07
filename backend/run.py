"""VisionFlywheel backend entry — start with `python run.py`."""

import os

import uvicorn


def main() -> None:
    host = os.getenv("VF_HOST", "127.0.0.1")
    port = int(os.getenv("VF_PORT", "8000"))
    reload = os.getenv("VF_RELOAD", "0") == "1"
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
