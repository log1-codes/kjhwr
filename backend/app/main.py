"""
backend/app/main.py

FastAPI application entrypoint for the UK Wind Day-Ahead Forecast & Actuals analytics portal.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes.api import router as api_router
from backend.app.data_service import data_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes in-memory Elexon cache upon server startup."""
    print("[*] Starting up: Loading Elexon BMRS dataset cache...")
    data_service.load_data()
    stats = data_service.get_stats()
    print(f"[✓] Cache ready: {stats['actuals_count']:,} FUELHH actuals, {stats['forecasts_count']:,} WINDFOR forecasts.")
    yield
    print("[*] Shutting down application.")


app = FastAPI(
    title="UK Day-Ahead Wind Forecast & Actuals Analytics API",
    description=(
        "Production-grade decision-support API for UK day-ahead wholesale electricity buyers. "
        "Reconciles National Grid ESO renewable generation forecasts (WINDFOR) with Elexon "
        "outturn meter data (FUELHH), evaluating error metrics at decision cutoff."
    ),
    version="1.0.0",
    lifespan=lifespan
)

import os

# Configure CORS with explicit origins or safe fallback
raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:80,http://127.0.0.1:3000,http://localhost"
)
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
is_wildcard = "*" in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not is_wildcard,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/", tags=["root"])
def root():
    """Root endpoint returning service identity and documentation link."""
    return {
        "service": "UK Day-Ahead Wind Analytics Platform",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_url": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
