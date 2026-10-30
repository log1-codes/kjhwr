"""
backend/app/routes/api.py

FastAPI route definitions for the UK Day-Ahead Wind Forecast & Actuals analytics portal.

Endpoints:
- GET /api/health: Service health and Elexon cache status.
- GET /api/actuals: Outturn wind generation (FUELHH) half-hourly data.
- GET /api/forecasts/latest: Latest wind forecasts (WINDFOR) available at configurable cutoff.
- GET /api/metrics: Evaluation metrics (MAE, RMSE, bias, nMAE, horizon degradation, aligned time-series).
- POST /api/refresh: Trigger on-demand sync from Elexon BMRS API (asynchronous, thread-safe).
"""

import os
from datetime import date
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Header
from fastapi.concurrency import run_in_threadpool

from backend.app.models import (
    HealthResponse,
    CacheStats,
    ActualsResponse,
    ActualRecord,
    ForecastsResponse,
    ForecastRecord,
    MetricsResponse,
    MetricsSummary,
    AlignedRecord,
    HorizonMetric
)
from backend.app.data_service import data_service
from backend.app.analysis import (
    select_latest_forecast_at_cutoff,
    join_forecasts_with_actuals,
    calculate_error_metrics,
    group_metrics_by_horizon,
    parse_iso_datetime
)

router = APIRouter(prefix="/api", tags=["analytics"])
REFRESH_SECRET = os.getenv("REFRESH_SECRET", "")


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Returns application health status and currently cached Elexon records count."""
    stats = data_service.get_stats()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        cache=CacheStats(**stats)
    )


@router.get("/actuals", response_model=ActualsResponse)
def get_actuals(
    start_date: Optional[date] = Query(None, description="Start settlement date YYYY-MM-DD (e.g. 2026-01-01)"),
    end_date: Optional[date] = Query(None, description="End settlement date YYYY-MM-DD (e.g. 2026-01-31)")
):
    """
    Returns actual half-hourly wind generation outturn (FUELHH) for target settlement dates.
    Default covers the entire month of January 2026 (1,488 half-hours).
    """
    s_date = start_date.isoformat() if start_date else "2026-01-01"
    e_date = end_date.isoformat() if end_date else "2026-01-31"

    records = data_service.get_actuals(start_date=s_date, end_date=e_date)
    actual_records = [
        ActualRecord(
            startTime=r["startTime"],
            settlementDate=r.get("settlementDate") or r["startTime"][:10],
            settlementPeriod=int(r.get("settlementPeriod", 1)),
            fuelType=r.get("fuelType", "WIND"),
            generation=float(r["generation"])
        )
        for r in records
    ]

    return ActualsResponse(
        metadata={
            "fuelType": "WIND",
            "start_date": s_date,
            "end_date": e_date,
            "record_count": len(actual_records)
        },
        data=actual_records
    )


@router.get("/forecasts/latest", response_model=ForecastsResponse)
def get_latest_forecasts(
    start_date: Optional[date] = Query(None, description="Start target delivery date YYYY-MM-DD (default: 2026-01-01)"),
    end_date: Optional[date] = Query(None, description="End target delivery date YYYY-MM-DD (default: 2026-01-31)"),
    cutoff_time: str = Query("09:00", pattern=r"^\d{2}:\d{2}$", description="Decision cutoff in UK local time HH:MM (default: 09:00, timezone-aware)"),
    cutoff_day_offset: int = Query(1, ge=0, le=7, description="Days prior to delivery (default: 1 for Day D-1)")
):
    """
    Returns the latest available wind forecast for each target delivery period
    based on the decision cutoff (default: 09:00 UK local time Europe/London on day D-1).
    Automatically accounts for winter GMT vs summer BST daylight savings transitions.
    """
    s_date = start_date.isoformat() if start_date else "2026-01-01"
    e_date = end_date.isoformat() if end_date else "2026-01-31"

    # Pre-filter forecasts by delivery target date range
    all_forecasts = data_service.get_forecasts(target_date_from=s_date, target_date_to=e_date)
    try:
        selected_by_st = select_latest_forecast_at_cutoff(
            all_forecasts,
            cutoff_time_str=cutoff_time,
            day_offset=cutoff_day_offset
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    results: list[ForecastRecord] = []
    for st_str, fc in sorted(selected_by_st.items()):
        st_dt = parse_iso_datetime(st_str)
        d_str = st_dt.strftime("%Y-%m-%d")
        if s_date <= d_str <= e_date:
            pub_dt = parse_iso_datetime(fc["publishTime"])
            lead_h = round((st_dt - pub_dt).total_seconds() / 3600.0, 2)

            # Settlement period calculation: hour * 2 + 1 for start of hour
            sp = st_dt.hour * 2 + 1

            results.append(
                ForecastRecord(
                    startTime=st_str,
                    settlementDate=d_str,
                    settlementPeriod=sp,
                    publishTime=fc["publishTime"],
                    generation=float(fc["generation"]),
                    horizonHours=lead_h
                )
            )

    return ForecastsResponse(
        metadata={
            "cutoff_time": cutoff_time,
            "cutoff_day_offset": cutoff_day_offset,
            "start_date": s_date,
            "end_date": e_date,
            "record_count": len(results)
        },
        data=results
    )


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    start_date: Optional[date] = Query(None, description="Start settlement date YYYY-MM-DD (default: 2026-01-01)"),
    end_date: Optional[date] = Query(None, description="End settlement date YYYY-MM-DD (default: 2026-01-31)"),
    cutoff_time: str = Query("09:00", pattern=r"^\d{2}:\d{2}$", description="Decision cutoff in UK local time HH:MM (default: 09:00, timezone-aware)"),
    cutoff_day_offset: int = Query(1, ge=0, le=7, description="Days prior to delivery (default: 1 for Day D-1)"),
    horizon_min: Optional[float] = Query(None, description="Optional filter: minimum horizon hours"),
    horizon_max: Optional[float] = Query(None, description="Optional filter: maximum horizon hours"),
    include_horizon: bool = Query(True, description="Include error metrics grouped by lead-time horizon"),
    include_series: bool = Query(True, description="Include aligned settlement time-series")
):
    """
    Evaluates forecast accuracy against actual outturn for a specified date range and decision cutoff.
    Computes MAE, RMSE, bias (mean error), capacity-normalized error, and lead-time horizon decay.
    Supports timezone-aware UK local cutoff conversion (Europe/London).
    """
    s_date = start_date.isoformat() if start_date else "2026-01-01"
    e_date = end_date.isoformat() if end_date else "2026-01-31"

    actuals = data_service.get_actuals(start_date=s_date, end_date=e_date)
    if not actuals:
        raise HTTPException(status_code=404, detail=f"No actuals found for date range {s_date} to {e_date}")

    # Pre-filter forecasts by delivery target date window
    all_forecasts = data_service.get_forecasts(target_date_from=s_date, target_date_to=e_date)
    try:
        selected_by_st = select_latest_forecast_at_cutoff(
            all_forecasts,
            cutoff_time_str=cutoff_time,
            day_offset=cutoff_day_offset
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    aligned = join_forecasts_with_actuals(actuals, selected_by_st)

    # Optional horizon filtering
    if horizon_min is not None:
        aligned = [r for r in aligned if r["horizonHours"] >= horizon_min]
    if horizon_max is not None:
        aligned = [r for r in aligned if r["horizonHours"] <= horizon_max]

    summary_dict = calculate_error_metrics(aligned)
    summary = MetricsSummary(**summary_dict)

    horizon_list = None
    if include_horizon and aligned:
        horizon_raw = group_metrics_by_horizon(aligned, bin_hours=4.0)
        horizon_list = [HorizonMetric(**h) for h in horizon_raw]

    series_list = None
    if include_series:
        series_list = [AlignedRecord(**r) for r in aligned]

    return MetricsResponse(
        metadata={
            "start_date": s_date,
            "end_date": e_date,
            "cutoff_time": cutoff_time,
            "cutoff_day_offset": cutoff_day_offset,
            "sample_count": len(aligned)
        },
        summary=summary,
        horizonMetrics=horizon_list,
        series=series_list
    )


@router.post("/refresh")
async def refresh_data(x_refresh_token: Optional[str] = Header(None)):
    """Trigger manual re-sync from Elexon BMRS API and reload in-memory cache asynchronously."""
    if REFRESH_SECRET and x_refresh_token != REFRESH_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing X-Refresh-Token")

    try:
        stats = await run_in_threadpool(data_service.refresh)
        return {"status": "refreshed", "cache": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh from Elexon: {str(e)}")
