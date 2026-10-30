"""
backend/main.py

Top-level service entrypoint for Vercel Services and local execution.
Re-exports the FastAPI app from backend.app.main.
"""

import sys
import os

# Ensure backend root is on Python search path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
