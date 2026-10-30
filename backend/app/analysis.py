"""
backend/app/analysis.py

Pure computational functions for power market analytics.
Zero web dependencies (no FastAPI, Starlette, or external network requests).

Core capabilities:
1. Decision cutoff forecast selection (latest WINDFOR run <= D-1 cutoff time).
2. Timezone-aware temporal alignment joining half-hourly actuals (FUELHH) with hourly forecasts.
3. Industry-standard quantitative metrics (MAE, RMSE, bias, capacity-normalized error, horizon decay).
"""

import math
import re
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Tuple

UK_TZ = ZoneInfo("Europe/London")


def parse_iso_datetime(dt_str: str) -> datetime:
    """
    Parses an ISO 8601 UTC timestamp string (e.g. '2026-01-01T00:30:00Z')
    into a timezone-aware UTC datetime object.
    """
    cleaned = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_cutoff_timestamp(delivery_date: date, cutoff_time_str: str = "09:00", day_offset: int = 1) -> datetime:
    """
    Computes the decision cutoff UTC timestamp for a given delivery date.
    
    In GB wholesale electricity trading, day-ahead purchase decisions for delivery day D
    are finalized on day D - day_offset (default: D-1) prior to auction gate closure.
    Cutoff time is defined in UK local time (Europe/London). During winter GMT this is UTC+0,
    and during summer British Summer Time (BST) this is UTC+1.
    The resulting timestamp is always converted to timezone-aware UTC.

    Example:
        delivery_date = 2026-01-02, cutoff_time = '09:00', day_offset = 1
        -> returns 2026-01-01 09:00:00 UTC (GMT)
        delivery_date = 2026-07-02, cutoff_time = '09:00', day_offset = 1
        -> returns 2026-07-01 08:00:00 UTC (BST)
    """
    if not re.match(r"^\d{2}:\d{2}$", cutoff_time_str):
        raise ValueError(f"Invalid cutoff time format: '{cutoff_time_str}'. Expected HH:MM")
    hour, minute = [int(p) for p in cutoff_time_str.split(":")]
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid cutoff time values: '{cutoff_time_str}'. Hour must be 00-23, minute 00-59")

    decision_date = delivery_date - timedelta(days=day_offset)
    decision_dt_local = datetime(
        decision_date.year, decision_date.month, decision_date.day,
        hour, minute, tzinfo=UK_TZ
    )
    return decision_dt_local.astimezone(timezone.utc)


def select_latest_forecast_at_cutoff(
    forecasts: List[Dict[str, Any]],
    cutoff_time_str: str = "09:00",
    day_offset: int = 1
) -> Dict[str, Dict[str, Any]]:
    """
    Selects the latest available wind forecast for each target delivery hour,
    subject to the trader's decision cutoff on day D - day_offset.

    Algorithm:
    1. Group all available forecast points by target delivery date D (derived from target startTime).
    2. Compute T_cutoff(D) = (D - day_offset) at cutoff_time_str.
    3. Filter candidate records whose publishTime <= T_cutoff(D).
    4. Best-practice Selection:
       Check if there is a single coherent forecast run (same publishTime) that covers all
       24 distinct hours of delivery day D. If so, select that latest complete run to prevent
       artificial ramp discontinuities.
       If no single run covers all 24 hours, fall back to selecting the latest valid
       forecast point for each hour independently.

    Returns:
        Dict mapping target startTime (ISO string, e.g. '2026-01-02T00:00:00Z') -> forecast record dict.
    """
    # 1. Group forecasts by target delivery date
    by_delivery_date: Dict[date, List[Dict[str, Any]]] = {}
    for f in forecasts:
        st_dt = parse_iso_datetime(f["startTime"])
        d = st_dt.date()
        by_delivery_date.setdefault(d, []).append(f)

    selected_forecasts: Dict[str, Dict[str, Any]] = {}

    for d, day_forecasts in by_delivery_date.items():
        t_cutoff = get_cutoff_timestamp(d, cutoff_time_str, day_offset)

        # Filter candidate records published on or before cutoff
        eligible: List[Dict[str, Any]] = []
        for f in day_forecasts:
            pub_dt = parse_iso_datetime(f["publishTime"])
            if pub_dt <= t_cutoff:
                eligible.append(f)

        if not eligible:
            continue

        # Check for coherent complete runs covering all 24 distinct hours of day d
        runs_by_publish: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for f in eligible:
            pt = f["publishTime"]
            runs_by_publish.setdefault(pt, {})[f["startTime"]] = f

        complete_runs = [
            pt for pt, hours_map in runs_by_publish.items()
            if len(set(parse_iso_datetime(st).hour for st in hours_map.keys())) == 24
        ]

        if complete_runs:
            # Pick latest complete coherent run
            latest_run_pt = max(complete_runs, key=parse_iso_datetime)
            for st, rec in runs_by_publish[latest_run_pt].items():
                selected_forecasts[st] = rec
        else:
            # Fallback: point-by-point latest available
            points_by_st: Dict[str, List[Dict[str, Any]]] = {}
            for f in eligible:
                points_by_st.setdefault(f["startTime"], []).append(f)

            for st, candidates in points_by_st.items():
                latest_point = max(candidates, key=lambda x: parse_iso_datetime(x["publishTime"]))
                selected_forecasts[st] = latest_point

    return selected_forecasts


def join_forecasts_with_actuals(
    actuals: List[Dict[str, Any]],
    forecasts_by_st: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Joins half-hourly actuals (FUELHH) with hourly decision-cutoff forecasts (WINDFOR).

    Granularity & Time Alignment:
    - FUELHH provides actual generation for each 30-minute settlement period (SP 1 to 48).
    - WINDFOR provides expected hourly generation.
    - Day-ahead power contracts trade in half-hourly settlement periods. In power trading,
      the hourly forecast for hour [H, H+1) is step forward-filled to apply to both
      constituent half-hours (e.g. 00:00 and 00:30 inherit the 00:00 hourly forecast).

    Error Definition:
    - error = forecastGeneration - actualGeneration (in MW)
    - Positive error (> 0): Over-forecast. Expected wind failed to materialize, leaving buyer short.
    - Negative error (< 0): Under-forecast. Actual wind exceeded forecast, leaving buyer long.
    """
    aligned_series: List[Dict[str, Any]] = []

    for act in actuals:
        st_str = act["startTime"]
        act_dt = parse_iso_datetime(st_str)
        act_mw = float(act["generation"])

        # Truncate to top of hour to match WINDFOR hourly resolution
        hour_key = act_dt.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:00:00Z")

        fc = forecasts_by_st.get(hour_key)
        if fc is None:
            # No forecast available at cutoff for this settlement period
            continue

        fc_mw = float(fc["generation"])
        pub_dt = parse_iso_datetime(fc["publishTime"])
        horizon_hours = round((act_dt - pub_dt).total_seconds() / 3600.0, 2)

        err_mw = round(fc_mw - act_mw, 2)
        abs_err_mw = round(abs(err_mw), 2)

        # Percentage error thresholded for periods with actual >= 100 MW
        pct_err: Optional[float] = None
        if act_mw >= 100.0:
            pct_err = round((abs_err_mw / act_mw) * 100.0, 2)

        aligned_series.append({
            "startTime": st_str,
            "settlementDate": act.get("settlementDate") or act_dt.strftime("%Y-%m-%d"),
            "settlementPeriod": int(act.get("settlementPeriod", 1)),
            "publishTime": fc["publishTime"],
            "actualGeneration": act_mw,
            "forecastGeneration": fc_mw,
            "error": err_mw,
            "absoluteError": abs_err_mw,
            "percentageError": pct_err,
            "horizonHours": horizon_hours
        })

    # Sort chronologically by parsed startTime (format-safe)
    aligned_series.sort(key=lambda x: parse_iso_datetime(x["startTime"]))
    return aligned_series


def calculate_error_metrics(
    records: List[Dict[str, Any]],
    installed_capacity_mw: float = 30500.0
) -> Dict[str, Any]:
    """
    Calculates comprehensive quantitative error metrics from aligned settlement records.

    Metrics:
    - MAE: Mean Absolute Error (MW)
    - RMSE: Root Mean Square Error (MW)
    - Bias: Mean forecast error (MW)
    - nMAE (Capacity): Normalized against total UK wind capacity (~30.5 GW in Jan 2026)
    - nMAE (Mean): Normalized against sample mean actual generation
    - MAPE (>100 MW): Filtered percentage error avoiding near-zero wind distortion
    - Energy (MWh): Calculated as sum(MW * 0.5 hours) for half-hourly data
    """
    n = len(records)
    if n == 0:
        return {
            "sampleCount": 0,
            "totalActualEnergyMWh": 0.0,
            "totalForecastEnergyMWh": 0.0,
            "meanActualMW": 0.0,
            "meanForecastMW": 0.0,
            "mae": 0.0,
            "rmse": 0.0,
            "bias": 0.0,
            "nmaeCapacity": 0.0,
            "nmaeMean": 0.0,
            "mapeThresholded": None,
            "maxOverforecastMW": 0.0,
            "maxUnderforecastMW": 0.0,
            "p90AbsoluteError": 0.0
        }

    actuals = [r["actualGeneration"] for r in records]
    forecasts = [r["forecastGeneration"] for r in records]
    errors = [r["error"] for r in records]
    abs_errors = [r["absoluteError"] for r in records]

    # Half-hourly power to energy: 1 MW for 30 minutes = 0.5 MWh
    total_act_mwh = round(sum(actuals) * 0.5, 2)
    total_fc_mwh = round(sum(forecasts) * 0.5, 2)

    mean_act = sum(actuals) / n
    mean_fc = sum(forecasts) / n

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
    bias = sum(errors) / n

    nmae_cap = (mae / installed_capacity_mw) * 100.0 if installed_capacity_mw > 0 else 0.0
    nmae_mean = (mae / mean_act) * 100.0 if mean_act > 0 else 0.0

    # Filtered percentage error for actuals >= 100 MW
    pct_errors = [r["percentageError"] for r in records if r.get("percentageError") is not None]
    mape_thresh = (sum(pct_errors) / len(pct_errors)) if pct_errors else None

    # Percentiles
    sorted_abs = sorted(abs_errors)
    p90_idx = int(math.ceil(0.90 * n)) - 1
    p90 = sorted_abs[max(0, min(p90_idx, n - 1))]

    return {
        "sampleCount": n,
        "totalActualEnergyMWh": total_act_mwh,
        "totalForecastEnergyMWh": total_fc_mwh,
        "meanActualMW": round(mean_act, 2),
        "meanForecastMW": round(mean_fc, 2),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "nmaeCapacity": round(nmae_cap, 2),
        "nmaeMean": round(nmae_mean, 2),
        "mapeThresholded": round(mape_thresh, 2) if mape_thresh is not None else None,
        "maxOverforecastMW": round(max(errors), 2),
        "maxUnderforecastMW": round(min(errors), 2),
        "p90AbsoluteError": round(p90, 2)
    }


def group_metrics_by_horizon(records: List[Dict[str, Any]], bin_hours: float = 4.0) -> List[Dict[str, Any]]:
    """
    Groups aligned records by lead-time horizon (hours between publication and settlement)
    into bins of width `bin_hours` and computes error metrics for each bin.
    """
    if not records:
        return []

    horizons = [r["horizonHours"] for r in records]
    min_h = math.floor(min(horizons) / bin_hours) * bin_hours
    max_h = math.ceil(max(horizons) / bin_hours) * bin_hours

    bins: Dict[Tuple[float, float], List[Dict[str, Any]]] = {}
    h_cursor = min_h
    while h_cursor < max_h:
        h_next = h_cursor + bin_hours
        bins[(h_cursor, h_next)] = []
        h_cursor = h_next

    for r in records:
        h = r["horizonHours"]
        for (b_start, b_end) in bins:
            if b_start <= h < b_end or (h == max_h and h <= b_end):
                bins[(b_start, b_end)].append(r)
                break

    results: List[Dict[str, Any]] = []
    for (b_start, b_end), bin_records in sorted(bins.items(), key=lambda x: x[0][0]):
        if not bin_records:
            continue
        errs = [r["error"] for r in bin_records]
        abs_errs = [r["absoluteError"] for r in bin_records]
        m = len(bin_records)
        mae = sum(abs_errs) / m
        rmse = math.sqrt(sum(e ** 2 for e in errs) / m)
        bias = sum(errs) / m

        results.append({
            "horizonBin": f"{int(b_start)}-{int(b_end)}h",
            "horizonMin": b_start,
            "horizonMax": b_end,
            "sampleCount": m,
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "bias": round(bias, 2)
        })

    return results
