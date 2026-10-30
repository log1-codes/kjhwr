#!/usr/bin/env python3
"""
scripts/explore_data.py

Fetches and explores UK wind generation actuals (FUELHH) and forecasts (WINDFOR)
from the Elexon BMRS API for January 2026 (including late December 2025 for day-ahead decisions).

Features:
- Handles Elexon API rate/date range limits by chunking requests.
- Saves raw JSON responses under data/raw/.
- Analyzes and prints:
  * Row counts and columns/keys
  * Min and max startTime and publishTime
  * Number of distinct publishTimes per target startTime (distribution + samples)
  * Gap detection (missing settlement periods or missing forecast horizons)
  * Alignment validation between half-hourly actuals and hourly forecasts
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def fetch_with_retry(url: str, params: Dict[str, Any], max_retries: int = 3, backoff_sec: float = 2.0) -> List[Dict[str, Any]]:
    """Fetches JSON stream data from Elexon API with retry and exponential backoff."""
    headers = {"User-Agent": "ElexonDataExplorer/1.0 (EnergyUtility-Evaluation)"}
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=45)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 500, 502, 503, 504):
                print(f"  [Attempt {attempt}/{max_retries}] Status {resp.status_code} for {url}. Waiting {backoff_sec}s...")
                time.sleep(backoff_sec)
                backoff_sec *= 2
            else:
                print(f"  [Error] HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
        except requests.RequestException as e:
            if attempt == max_retries:
                raise
            print(f"  [Attempt {attempt}/{max_retries}] Network error: {e}. Retrying in {backoff_sec}s...")
            time.sleep(backoff_sec)
            backoff_sec *= 2
    return []


def fetch_fuelhh_data(start_date: str = "2025-12-31", end_date: str = "2026-02-01", chunk_days: int = 7) -> List[Dict[str, Any]]:
    """
    Fetches actual half-hourly wind generation from FUELHH/stream in chunked settlement date ranges.
    Includes 2025-12-31 and 2026-02-01 to provide complete boundary coverage for January 2026 decisions.
    """
    cache_file = os.path.join(DATA_DIR, "fuelhh_raw.json")
    if os.path.exists(cache_file):
        print(f"[*] Found cached FUELHH data at {cache_file}, loading...")
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"[*] Fetching FUELHH actuals from {start_date} to {end_date} (fuelType=WIND, chunks={chunk_days} days)...")
    url = f"{BASE_URL}/datasets/FUELHH/stream"
    
    dt_current = datetime.strptime(start_date, "%Y-%m-%d")
    dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    
    all_records: List[Dict[str, Any]] = []
    chunk_idx = 1
    
    while dt_current <= dt_end:
        dt_chunk_end = min(dt_current + timedelta(days=chunk_days - 1), dt_end)
        s_from = dt_current.strftime("%Y-%m-%d")
        s_to = dt_chunk_end.strftime("%Y-%m-%d")
        
        params = {
            "settlementDateFrom": s_from,
            "settlementDateTo": s_to,
            "fuelType": "WIND"
        }
        print(f"  Fetching chunk {chunk_idx}: {s_from} to {s_to}...", end="", flush=True)
        chunk_data = fetch_with_retry(url, params)
        print(f" received {len(chunk_data)} records.")
        all_records.extend(chunk_data)
        
        dt_current = dt_chunk_end + timedelta(days=1)
        chunk_idx += 1
        time.sleep(0.3)

    # Deduplicate by (settlementDate, settlementPeriod, fuelType)
    seen = set()
    deduped = []
    for r in all_records:
        key = (r.get("settlementDate"), r.get("settlementPeriod"), r.get("fuelType"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Sort chronologically by startTime
    deduped.sort(key=lambda x: x.get("startTime", ""))

    print(f"[*] Total FUELHH records collected: {len(deduped)} (raw: {len(all_records)})")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2)
    print(f"[*] Saved raw FUELHH data to {cache_file}")
    return deduped


def fetch_windfor_data(start_publish: str = "2025-12-30T00:00:00Z", end_publish: str = "2026-02-01T23:59:59Z", chunk_days: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches wind generation forecasts from WINDFOR/stream in chunked publishDateTime ranges.
    Includes publications starting from Dec 30, 2025 to cover day-ahead decisions made on Dec 31
    for Jan 1 delivery.
    """
    cache_file = os.path.join(DATA_DIR, "windfor_raw.json")
    if os.path.exists(cache_file):
        print(f"[*] Found cached WINDFOR data at {cache_file}, loading...")
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"[*] Fetching WINDFOR forecasts from {start_publish} to {end_publish} (chunks={chunk_days} days)...")
    url = f"{BASE_URL}/datasets/WINDFOR/stream"
    
    dt_current = datetime.fromisoformat(start_publish.replace("Z", "+00:00"))
    dt_end = datetime.fromisoformat(end_publish.replace("Z", "+00:00"))
    
    all_records: List[Dict[str, Any]] = []
    chunk_idx = 1
    
    while dt_current < dt_end:
        dt_chunk_end = min(dt_current + timedelta(days=chunk_days), dt_end)
        s_from = dt_current.strftime("%Y-%m-%dT%H:%M:%SZ")
        s_to = dt_chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        params = {
            "publishDateTimeFrom": s_from,
            "publishDateTimeTo": s_to
        }
        print(f"  Fetching chunk {chunk_idx}: {s_from} to {s_to}...", end="", flush=True)
        chunk_data = fetch_with_retry(url, params)
        print(f" received {len(chunk_data)} records.")
        all_records.extend(chunk_data)
        
        dt_current = dt_chunk_end
        chunk_idx += 1
        time.sleep(0.3)

    # Deduplicate by (publishTime, startTime)
    seen = set()
    deduped = []
    for r in all_records:
        key = (r.get("publishTime"), r.get("startTime"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    deduped.sort(key=lambda x: (x.get("publishTime", ""), x.get("startTime", "")))

    print(f"[*] Total WINDFOR records collected: {len(deduped)} (raw: {len(all_records)})")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2)
    print(f"[*] Saved raw WINDFOR data to {cache_file}")
    return deduped


def explore_fuelhh(records: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print(" 1. FUELHH (ACTUAL WIND OUTTURN) EXPLORATION")
    print("=" * 80)
    
    if not records:
        print("[!] No FUELHH records found.")
        return

    print(f"Row count: {len(records):,}")
    print(f"Columns / Keys: {list(records[0].keys())}")
    
    start_times = [r["startTime"] for r in records if "startTime" in r]
    publish_times = [r["publishTime"] for r in records if "publishTime" in r]
    generations = [r["generation"] for r in records if r.get("generation") is not None]
    
    min_st, max_st = min(start_times), max(start_times)
    min_pt, max_pt = min(publish_times), max(publish_times)
    
    print(f"startTime range:   {min_st}  -->  {max_st}")
    print(f"publishTime range: {min_pt}  -->  {max_pt}")
    
    if generations:
        avg_gen = sum(generations) / len(generations)
        print(f"Generation (MW):   Min = {min(generations):,} MW | Max = {max(generations):,} MW | Mean = {avg_gen:,.1f} MW")

    # Settlement period coverage across January 2026
    jan_records = [r for r in records if r.get("settlementDate", "").startswith("2026-01")]
    print(f"\nJanuary 2026 specific records: {len(jan_records):,} (Expected for 31 days x 48 SP = 1,488)")
    
    # Gap Detection in FUELHH
    print("\n--- FUELHH Gap Detection ---")
    st_set = set(start_times)
    dt_cursor = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_end = datetime(2026, 1, 31, 23, 30, tzinfo=timezone.utc)
    
    missing_intervals = []
    total_expected = 0
    while dt_cursor <= dt_end:
        iso_str = dt_cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        total_expected += 1
        if iso_str not in st_set:
            missing_intervals.append(iso_str)
        dt_cursor += timedelta(minutes=30)
        
    if missing_intervals:
        print(f"[!] GAPS DETECTED in January 2026: {len(missing_intervals)} missing settlement periods!")
        print(f"    Missing sample: {missing_intervals[:10]}")
    else:
        print(f"[✓] Zero gaps detected! All {total_expected} half-hour settlement periods in January 2026 are present.")

    # Distinct publishTimes per startTime
    st_to_pts = {}
    for r in records:
        st = r["startTime"]
        st_to_pts.setdefault(st, set()).add(r["publishTime"])
    
    distinct_pt_counts = [len(pts) for pts in st_to_pts.values()]
    print(f"\nDistinct publishTimes per startTime: Min={min(distinct_pt_counts)}, Max={max(distinct_pt_counts)}, Avg={sum(distinct_pt_counts)/len(distinct_pt_counts):.2f}")
    print("Note: FUELHH is outturn meter data; each settlement period is finalized and published once by Elexon.")


def explore_windfor(records: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print(" 2. WINDFOR (WIND FORECAST RUNS) EXPLORATION")
    print("=" * 80)
    
    if not records:
        print("[!] No WINDFOR records found.")
        return

    print(f"Row count: {len(records):,}")
    print(f"Columns / Keys: {list(records[0].keys())}")
    
    start_times = [r["startTime"] for r in records if "startTime" in r]
    publish_times = [r["publishTime"] for r in records if "publishTime" in r]
    generations = [r["generation"] for r in records if r.get("generation") is not None]
    
    min_st, max_st = min(start_times), max(start_times)
    min_pt, max_pt = min(publish_times), max(publish_times)
    
    print(f"startTime range:   {min_st}  -->  {max_st}")
    print(f"publishTime range: {min_pt}  -->  {max_pt}")
    
    distinct_runs = sorted(set(publish_times))
    print(f"Total distinct forecast publication runs: {len(distinct_runs)}")
    
    if generations:
        avg_gen = sum(generations) / len(generations)
        print(f"Forecast Generation (MW): Min = {min(generations):,} MW | Max = {max(generations):,} MW | Mean = {avg_gen:,.1f} MW")

    # Analyze distinct publishTimes per startTime
    st_to_pts: Dict[str, List[str]] = {}
    for r in records:
        st = r["startTime"]
        st_to_pts.setdefault(st, []).append(r["publishTime"])

    pt_counts = [len(pts) for pts in st_to_pts.values()]
    avg_pt = sum(pt_counts) / len(pt_counts) if pt_counts else 0
    print(f"\nDistinct publishTimes per startTime:")
    print(f"  Total unique target startTimes: {len(st_to_pts):,}")
    print(f"  Min publishTimes per startTime: {min(pt_counts)}")
    print(f"  Max publishTimes per startTime: {max(pt_counts)}")
    print(f"  Average publishTimes per startTime: {avg_pt:.1f}")

    # Inspect January 2026 target hours
    jan_target_hours = [st for st in st_to_pts.keys() if st.startswith("2026-01")]
    jan_target_counts = [len(st_to_pts[st]) for st in jan_target_hours]
    if jan_target_counts:
        print(f"\nFor January 2026 target hours ({len(jan_target_hours)} hours):")
        print(f"  Min runs per hour: {min(jan_target_counts)}")
        print(f"  Max runs per hour: {max(jan_target_counts)}")
        print(f"  Average runs per hour: {sum(jan_target_counts)/len(jan_target_counts):.1f}")

    # Show a concrete sample of how a target hour evolves across forecast runs
    sample_st = "2026-01-15T12:00:00Z"
    if sample_st in st_to_pts:
        print(f"\n--- Forecast Evolution Sample for target {sample_st} ---")
        st_records = [r for r in records if r["startTime"] == sample_st]
        st_records.sort(key=lambda x: x["publishTime"])
        print(f"{'Publish Time (UTC)':<24} | {'Lead Time (h)':<14} | {'Forecast (MW)':<14}")
        print("-" * 58)
        target_dt = datetime.fromisoformat(sample_st.replace("Z", "+00:00"))
        # Show first 3, middle 2, and last 3 runs
        indices = list(range(min(3, len(st_records)))) + \
                  list(range(max(3, len(st_records)//2 - 1), min(len(st_records)-3, len(st_records)//2 + 1))) + \
                  list(range(max(0, len(st_records)-3), len(st_records)))
        seen_idx = set()
        for idx in indices:
            if idx in seen_idx or idx >= len(st_records):
                continue
            seen_idx.add(idx)
            rec = st_records[idx]
            pt = rec["publishTime"]
            pt_dt = datetime.fromisoformat(pt.replace("Z", "+00:00"))
            lead_h = (target_dt - pt_dt).total_seconds() / 3600.0
            print(f"{pt:<24} | {lead_h:<14.1f} | {rec['generation']:<14,}")

    # Gap Detection in WINDFOR
    print("\n--- WINDFOR Gap Detection for January 2026 ---")
    dt_cursor = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_end = datetime(2026, 1, 31, 23, 0, tzinfo=timezone.utc)
    
    missing_hours = []
    missing_day_ahead_cutoff = []
    total_hours = 0
    
    # Pre-organize WINDFOR by target startTime and its publishTimes
    # For day D, cutoff is D-1 at 09:00 UK time (Europe/London).
    # Since January is GMT (UTC+0), cutoff is (D - 1 day) 09:00:00Z.
    while dt_cursor <= dt_end:
        total_hours += 1
        iso_str = dt_cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if iso_str not in st_to_pts:
            missing_hours.append(iso_str)
        else:
            # Check if there is at least one forecast available before D-1 09:00 GMT
            delivery_date = dt_cursor.date()
            decision_date = delivery_date - timedelta(days=1)
            cutoff_dt = datetime(decision_date.year, decision_date.month, decision_date.day, 9, 0, tzinfo=timezone.utc)
            
            pts_for_hour = [datetime.fromisoformat(pt.replace("Z", "+00:00")) for pt in st_to_pts[iso_str]]
            eligible_pts = [pt for pt in pts_for_hour if pt <= cutoff_dt]
            if not eligible_pts:
                missing_day_ahead_cutoff.append(iso_str)
                
        dt_cursor += timedelta(hours=1)

    if missing_hours:
        print(f"[!] GAPS DETECTED: {len(missing_hours)} target hours in January have 0 forecasts.")
    else:
        print(f"[✓] Zero total gaps: All {total_hours} target hours in January 2026 have forecast data.")

    if missing_day_ahead_cutoff:
        print(f"[!] CUTOFF GAPS DETECTED: {len(missing_day_ahead_cutoff)} target hours lack a forecast published <= D-1 09:00 GMT.")
        print(f"    Sample: {missing_day_ahead_cutoff[:5]}")
    else:
        print(f"[✓] Zero day-ahead cutoff gaps: 100% of January 2026 target hours ({total_hours}/{total_hours}) have at least one forecast published on or before D-1 09:00 GMT!")


def explore_alignment(fuelhh: List[Dict[str, Any]], windfor: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 80)
    print(" 3. ALIGNMENT VALIDATION (HALF-HOURLY ACTUALS VS HOURLY FORECASTS)")
    print("=" * 80)
    
    # Build lookup of latest forecast published <= D-1 09:00 GMT for each hour
    windfor_by_st: Dict[str, List[Dict[str, Any]]] = {}
    for r in windfor:
        windfor_by_st.setdefault(r["startTime"], []).append(r)
        
    cutoff_forecast: Dict[str, Dict[str, Any]] = {}
    for st, runs in windfor_by_st.items():
        st_dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
        delivery_date = st_dt.date()
        cutoff_dt = datetime(delivery_date.year, delivery_date.month, delivery_date.day, 9, 0, tzinfo=timezone.utc) - timedelta(days=1)
        
        eligible = [r for r in runs if datetime.fromisoformat(r["publishTime"].replace("Z", "+00:00")) <= cutoff_dt]
        if eligible:
            latest = max(eligible, key=lambda x: x["publishTime"])
            cutoff_forecast[st] = latest

    print(f"Total target hours with valid D-1 09:00 forecast: {len(cutoff_forecast):,}")
    
    # Step Forward-Fill Alignment on Sample Day (2026-01-01)
    print("\nSample Alignment for 2026-01-01 (Settlement Periods 1 through 6):")
    print(f"{'SP':<4} | {'Target (startTime)':<21} | {'Actual (MW)':<12} | {'Forecast (MW)':<14} | {'Error (MW)':<12} | {'Matched Run':<20}")
    print("-" * 92)
    
    jan1_actuals = [r for r in fuelhh if r.get("settlementDate") == "2026-01-01"]
    for act in jan1_actuals[:6]:
        sp = act["settlementPeriod"]
        st = act["startTime"]
        act_mw = act["generation"]
        
        # Truncate startTime to top of hour to match WINDFOR
        st_dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
        hour_key = st_dt.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:00:00Z")
        
        fc = cutoff_forecast.get(hour_key)
        if fc:
            fc_mw = fc["generation"]
            err = fc_mw - act_mw
            pt = fc["publishTime"]
            print(f"{sp:<4} | {st:<21} | {act_mw:<12,} | {fc_mw:<14,} | {err:<+12,} | {pt:<20}")
        else:
            print(f"{sp:<4} | {st:<21} | {act_mw:<12,} | {'MISSING':<14} | {'N/A':<12} | {'N/A':<20}")

    print("\n" + "=" * 80)
    print(" EXPLORATION COMPLETE")
    print("=" * 80 + "\n")


def main() -> None:
    ensure_data_dir()
    print("================================================================================")
    print(" ELEXON BMRS DATA EXPLORER & INGESTION SCRIPT")
    print("================================================================================")
    
    # 1. Fetch FUELHH Actuals
    fuelhh_data = fetch_fuelhh_data(start_date="2025-12-31", end_date="2026-02-01", chunk_days=7)
    
    # 2. Fetch WINDFOR Forecasts
    windfor_data = fetch_windfor_data(start_publish="2025-12-30T00:00:00Z", end_publish="2026-02-01T23:59:59Z", chunk_days=5)
    
    # 3. Explore FUELHH
    explore_fuelhh(fuelhh_data)
    
    # 4. Explore WINDFOR
    explore_windfor(windfor_data)
    
    # 5. Explore Alignment
    explore_alignment(fuelhh_data, windfor_data)


if __name__ == "__main__":
    main()
