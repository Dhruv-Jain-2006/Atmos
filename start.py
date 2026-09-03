"""Production startup script for Railway.

Reads the PORT environment variable that Railway injects and starts uvicorn.
This avoids shell variable expansion issues across different contexts
(Dockerfile CMD vs railway.json startCommand vs Railway process manager).
"""

import os
import sys


def main() -> None:
    port = os.environ.get("PORT", "8000")
    host = "0.0.0.0"

    print(f"Starting uvicorn on {host}:{port}", flush=True)

    # Import uvicorn here so the print statement is visible even if import fails
    import uvicorn

    uvicorn.run(
        "backend.internetweather.api.app:app",
        host=host,
        port=int(port),
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
