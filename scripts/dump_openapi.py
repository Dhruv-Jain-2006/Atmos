"""Write the OpenAPI document to docs/openapi.json.

No server and no database required — the document is derived from the FastAPI
app object. The frontend's TypeScript types are generated from this file, so the
committed contract is what the UI is built against and any drift shows up as a
reviewable diff rather than a runtime surprise.

    uv run python scripts/dump_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from internetweather.api.app import create_app  # noqa: E402

OUTPUT = REPO_ROOT / "docs" / "openapi.json"


def main() -> int:
    document = create_app().openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"{OUTPUT.relative_to(REPO_ROOT)}: {len(document['paths'])} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
