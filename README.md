# UK Day-Ahead Wind Forecast & Actuals Analytics Platform

> **Live Deployment:** [https://kjhwr-kappa-three.vercel.app](https://kjhwr-kappa-three.vercel.app)  
> **Interactive API Docs:** [https://kjhwr-kappa-three.vercel.app/docs](https://kjhwr-kappa-three.vercel.app/docs)  
> **Evaluation Period:** January 2026 (1,488 settlement periods)  
> **Target Audience:** UK Wholesale Day-Ahead Power Buyers (EPEX Spot / Nord Pool)

---

## 1. Project Overview

In the Great Britain wholesale electricity market, day-ahead power buyers procure energy on power exchanges (e.g., EPEX Spot Day-Ahead Auction at 11:00 UK time) to match customer demand while hedging intermittent renewable generation. Because wind generation cannot be scheduled on demand, buyers rely on national wind generation forecasts to determine their net open positions.

This analytics portal reconciles:
1. **National Grid ESO Wind Forecasts (`WINDFOR`)**: Hourly expected wind generation published ~every 2–4 hours with 72+ hour horizons.
2. **Elexon Outturn Meter Data (`FUELHH`)**: Actual half-hourly wind generation per settlement period (SP 1 to 48).

The platform evaluates the **forecast accuracy at the buyer's decision cutoff** (default: **09:00 UK local time on Day D-1**), calculating key quantitative risk metrics (MAE, RMSE, bias, capacity-normalized error, and lead-time horizon degradation) to assist trading desks in calculating imbalance exposure and volume risk.

---

## 2. Key Domain Decisions & Assumptions

### Decision Cutoff Logic
- **Auction Gate Closure Timing:** The EPEX Day-Ahead auction order book closes at 11:00 GMT (12:00 CET) on day D-1. Trading desks must finalize fundamental bidding models and submit balance curves by mid-morning.
- **Configurable Cutoff:** Defaulted to **09:00 UK local time on Day D-1** (`cutoff_time=09:00`, `cutoff_day_offset=1`).
- **Coherent Run Selection:** At decision cutoff $T_{\text{cutoff}}(D)$, the algorithm searches candidate forecasts where $\text{publishTime} \le T_{\text{cutoff}}(D)$. If a complete 24-hour run (same $\text{publishTime}$ covering all 24 distinct hours of day $D$) exists, it is selected to prevent artificial intra-day ramp discontinuities. If no single run covers all 24 hours, the algorithm falls back to selecting the latest available forecast point per individual hour.

### Granularity & Temporal Alignment
- **Half-Hourly vs. Hourly Resolution:** `FUELHH` actuals are measured half-hourly (30-minute settlement periods). `WINDFOR` is published at hourly resolution.
- **Step Forward-Fill:** Under standard power trading convention, the hourly forecast for hour $[H, H+1)$ applies to both constituent settlement periods (e.g., settlement period $2H+1$ and $2H+2$ at :00 and :30 both inherit the :00 hourly forecast).
- **Timezone & Daylight Savings:** All inputs are converted using Python stdlib `zoneinfo.ZoneInfo("Europe/London")` to timezone-aware UTC. During winter GMT (January), 09:00 UK is 09:00 UTC; during British Summer Time (BST), 09:00 UK local is 08:00 UTC.

### Error Definitions & Economic Significance
- **Error Formula:**  
  $$\text{Error} = \text{Forecast Generation} - \text{Actual Generation} \quad (\text{MW})$$
- **Directional Bias Interpretation:**
  - **Positive Error ($> 0$ / Over-forecast):** Wind generation failed to materialize. A day-ahead buyer who bought less power expecting wind is left **SHORT** into the System Price (Cashout) imbalance market.
  - **Negative Error ($< 0$ / Under-forecast):** Wind generation exceeded forecast. The buyer is left **LONG**, spilling power back to the grid.
- **Power to Energy Conversion:**  
  $$\text{Energy (MWh)} = \sum \left( \text{Generation (MW)} \times 0.5\text{ hours} \right)$$

### Quantitative Metrics
- **MAE (Mean Absolute Error):** Average magnitude of volume error in MW.
- **RMSE (Root Mean Square Error):** Penalizes extreme forecast ramp busts.
- **Bias (Mean Error):** Indicates systematic over- or under-forecasting by National Grid ESO.
- **nMAE (Capacity):** Normalized against GB total installed wind capacity (~30,500 MW in January 2026).
- **nMAE (Mean):** Normalized against average actual wind generation during the selected period.
- **Thresholded MAPE:** Filtered percentage error evaluated exclusively for half-hours with $\text{Actual} \ge 100\text{ MW}$ to avoid infinite distortion near calm winds.
- **Lead-Time Horizon Decay:** Errors grouped into 4-hour lead-time bins ($\text{horizon} = \text{startTime} - \text{publishTime}$) to quantify uncertainty reduction closer to delivery.

### January 2026 Market Outturn Findings
At the standard 09:00 D-1 decision cutoff for January 2026:
- **Actual Wind Energy:** 8,616,068.5 MWh (Mean: 11,580.7 MW)
- **Forecast Wind Energy:** 9,993,885.0 MWh (Mean: 13,432.6 MW)
- **MAE:** 2,145.2 MW | **RMSE:** 2,615.8 MW
- **Bias:** **+1,851.9 MW** (National Grid ESO persistently over-forecasted wind generation, leaving day-ahead buyers systematically **SHORT** by ~1.38 TWh).

---

## 3. Repository Architecture & Directory Structure

```
├── api/
│   └── index.py                     # Vercel Serverless Function entrypoint (FastAPI ASGI)
├── backend/
│   ├── Dockerfile                   # Production Python 3.11-slim container
│   ├── requirements.txt             # Pinned production runtime dependencies
│   ├── requirements-dev.txt         # Testing and development dependencies (pytest, httpx)
│   ├── .dockerignore                # Container build exclusions (.venv, caches, tests)
│   ├── data/                        # Pre-cached Elexon BMRS January 2026 data
│   │   ├── fuelhh_raw.json          # 1,584 FUELHH actual records (Dec 31 2025 - Feb 1 2026)
│   │   └── windfor_raw.json         # 19,856 WINDFOR forecast records (272 publish runs)
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS middleware, lifespan cache loader
│   │   ├── models.py                # Pydantic schemas (requests, responses, KPI metrics)
│   │   ├── analysis.py              # Pure domain logic: cutoff selection, alignment, metrics
│   │   ├── data_service.py          # Thread-safe in-memory cache, lazy loader, chunked refresh
│   │   └── routes/
│   │       └── api.py               # REST endpoints (/health, /actuals, /forecasts, /metrics, /refresh)
│   └── tests/
│       ├── test_analysis.py         # 46 unit tests (cutoff, coherent runs, DST, hand-calculated math)
│       └── test_api.py              # 8 integration tests (FastAPI TestClient, validation, auth)
├── frontend/
│   ├── Dockerfile                   # Multi-stage production container (Node 20 builder -> Nginx Alpine)
│   ├── nginx.conf.template          # Nginx reverse proxy template forwarding /api to backend
│   ├── .dockerignore                # Node build context exclusions (node_modules, dist)
│   ├── package.json                 # React 18, Vite, TypeScript, Recharts
│   └── src/
│       ├── App.tsx                  # State coordination, loading overlay, filter controls
│       ├── api.ts                   # Fetch wrapper with relative /api resolution
│       ├── types.ts                 # TypeScript data contracts matching backend Pydantic models
│       ├── index.css                # Dark-mode professional energy trading terminal theme
│       └── components/
│           ├── Header.tsx           # Dashboard title, market status, trading badge
│           ├── Controls.tsx         # Date pickers, D-1 cutoff selector, quick presets
│           ├── MetricsCards.tsx     # MAE, RMSE, Bias (SHORT/LONG pill), nMAE metrics
│           ├── TimeSeriesChart.tsx  # Actual vs Forecast chart with settlement period details
│           ├── HorizonChart.tsx     # Error vs Lead-Time horizon degradation bar chart
│           ├── TraderGuide.tsx      # Desk reference guide explaining power market mechanics
│           └── StatusStates.tsx     # Loading overlay and error boundary display
├── data/raw/                        # Canonical raw Elexon dataset cache
├── docs/
│   ├── ASSIGNMENT.md                # Problem statement and requirements
│   └── PLAN.md                      # Technical design specifications and execution roadmap
├── scripts/
│   └── explore_data.py              # Initial data ingestion exploration script
├── docker-compose.yml               # Production container orchestration with health checks
├── docker-compose.override.yml      # Development override for local live reload and volume mount
├── vercel.json                      # Vercel deployment blueprint (static Vite SPA + Python API)
├── render.yaml                      # Render blueprint for Docker Web Service backend
├── pytest.ini                       # Test discovery and pythonpath configuration
└── requirements.txt                 # Root requirements file for Vercel Python builder
```

---

## 4. How to Start

### Option A: With Docker (Recommended for Local Dev)

Ensure Docker and Docker Compose are installed.

```bash
# 1. Build and start both backend (port 8000) and frontend (port 3000)
docker compose up -d

# 2. View live service status and healthcheck
docker compose ps

# 3. Stream container logs
docker compose logs -f

# 4. Tear down containers
docker compose down
```

- **Frontend Application:** Open [http://localhost:3000](http://localhost:3000)
- **Backend API Docs:** Open [http://localhost:8000/docs](http://localhost:8000/docs)
- **Direct Healthcheck:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

*(Note: Live file mounting and uvicorn hot-reload are active automatically via `docker-compose.override.yml`)*

---

### Option B: Without Docker (Local Bare-Metal)

#### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

#### 1. Backend Setup
```bash
# From repository root:
python3 -m venv .venv
source .venv/bin/activate

# Install development and testing dependencies
pip install -r backend/requirements-dev.txt

# Start backend server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API runs on [http://localhost:8000](http://localhost:8000) (interactive OpenAPI documentation at `/docs`).

#### 2. Frontend Setup
```bash
# In a separate terminal:
cd frontend
npm install
npm run dev
```
Vite dev server runs on [http://localhost:5173](http://localhost:5173) with automatic proxying to `http://localhost:8000`.

---

## 5. Running the Test Suite

The test suite validates:
- Cutoff selection logic (latest run at or before cutoff; exclusion of post-cutoff runs).
- Coherent 24-hour run preference vs. fallback point-by-point selection.
- DST clock changes (Europe/London conversion across GMT and BST).
- Temporal alignment (half-hourly step forward-fill, missing forecast drop).
- Mathematical error metrics (MAE, RMSE, bias, nMAE, thresholded MAPE, MWh energy) verified against hand-calculated synthetic data.
- API validation (422 Unprocessable Entity for invalid date formats and cutoff regex mismatch).
- Refresh authentication (403 Forbidden when secret is configured).

```bash
# Activate virtual environment
source .venv/bin/activate

# Execute all 54 tests
pytest backend/tests/ -v
```

Expected output:
```
======================== 54 passed, 1 warning in 0.52s =========================
```

---

## 6. Live Deployment Guide

### Vercel (All-in-One Fullstack)
The repository is pre-configured with [`vercel.json`](file:///home/singhanurag/kjhwr/vercel.json) and [`api/index.py`](file:///home/singhanurag/kjhwr/api/index.py):

```bash
# Install Vercel CLI and deploy
npm install -g vercel
vercel login
vercel --prod
```

### Render + Vercel (Alternative Container Deployment)
- **Backend on Render:** Connect the repository to [Render](https://render.com) using Blueprint. Render detects [`render.yaml`](file:///home/singhanurag/kjhwr/render.yaml) and deploys `backend/Dockerfile`.
- **Frontend on Vercel:** Deploy `frontend/` on Vercel and set `VITE_API_BASE_URL=https://<your-render-app>.onrender.com`.

---

## 7. AI Tools Disclosure

In accordance with transparent engineering practices:
- **Google DeepMind Antigravity 2.0 (Gemini 3.8 Flash):** Used as the primary agentic pair programmer for data ingestion exploration, API route architecture, pure computation analytics module implementation, frontend dashboard development (React, Vite, Recharts), Docker multi-stage containerization, and Vercel serverless preparation.
- **Claude Opus 4.6:** Engaged in a senior tech lead review capacity to conduct adversarial domain logic stress-testing, identify boundary and timezone edge cases (BST transition, event-loop blocking, CORS specs), and formulate comprehensive verification test cases.
