import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import settings

if __name__ == "__main__":
    print(f"Sol scanner API on http://localhost:{settings.API_PORT}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.API_PORT, reload=False)
