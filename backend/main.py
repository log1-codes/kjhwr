"""
backend/main.py

Top-level service entrypoint for Vercel Services and local execution.
Re-exports the FastAPI app from backend.app.main.
"""

import sys
import os
import types

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Register 'backend' package alias so all existing 'backend.app...' imports work inside Vercel
if "backend" not in sys.modules:
    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [BACKEND_DIR]
    sys.modules["backend"] = backend_pkg

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
