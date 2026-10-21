"""Write the API's OpenAPI schema to frontend/openapi.json, for generating the zod schemas.

Usage (from backend/): uv run python -m scripts.export_openapi
Then (from frontend/): npm run gen:api
"""

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
