"""
api/index.py

Vercel Serverless Function entrypoint.
Exports the FastAPI application instance for Vercel's Python runtime.
"""

import sys
import os

# Add repository root to Python path so 'backend' package is resolvable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Ensure DATA_DIR points to the bundled pre-cached market datasets
if not os.getenv("DATA_DIR"):
    for candidate in [
        os.path.join(ROOT_DIR, "backend", "data"),
        os.path.join(ROOT_DIR, "data", "raw"),
        os.path.join(ROOT_DIR, "data"),
    ]:
        if os.path.exists(os.path.join(candidate, "fuelhh_raw.json")):
            os.environ["DATA_DIR"] = candidate
            break

from backend.app.main import app
