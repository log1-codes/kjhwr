# backend/app/__init__.py
import sys
import os
import types

# Ensure backend root is in sys.path and aliased as 'backend' for Vercel Services
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if "backend" not in sys.modules:
    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [BACKEND_DIR]
    sys.modules["backend"] = backend_pkg
