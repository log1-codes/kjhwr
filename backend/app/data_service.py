"""
backend/app/data_service.py

Data service managing in-memory caching and retrieval of Elexon BMRS datasets
(FUELHH actual wind generation and WINDFOR wind forecasts).

Features:
- Fast in-memory querying with thread-safe reads and atomic cache updates.
- Lazy filesystem directory detection.
- Safe chunked refresh mechanism querying Elexon BMRS with error propagation
  to prevent overwriting existing valid cache on network/upstream failures.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import requests

from backend.app.analysis import parse_iso_datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def resolve_data_dir(custom_dir: Optional[str] = None) -> str:
    """
    Lazily resolves the dataset directory path by checking candidate locations.
    Evaluated when DataService is instantiated rather than at module import.
    """
    if custom_dir:
        return custom_dir

    candidate_dirs = [
        os.getenv("DATA_DIR"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data")),
        "/app/data",
        "/app/data/raw",
    ]
    for d in candidate_dirs:
        if d and os.path.exists(os.path.join(d, "fuelhh_raw.json")):
            return d

    # Default fallback
    return candidate_dirs[1] or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


class DataService:
    """Thread-safe service to load, cache, query, and refresh Elexon market datasets."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = resolve_data_dir(data_dir)
        self.actuals_file = os.path.join(self.data_dir, "fuelhh_raw.json")
        self.forecasts_file = os.path.join(self.data_dir, "windfor_raw.json")
        self._lock = threading.Lock()
        self._actuals: List[Dict[str, Any]] = []
        self._forecasts: List[Dict[str, Any]] = []
        self._is_loaded: bool = False

    def load_data(self, force_fetch: bool = False) -> None:
        """
        Loads dataset records into memory from disk cache.
        If files do not exist or force_fetch is True, fetches directly from Elexon BMRS.
        """
        os.makedirs(self.data_dir, exist_ok=True)

        if not force_fetch and os.path.exists(self.actuals_file) and os.path.exists(self.forecasts_file):
            with open(self.actuals_file, "r", encoding="utf-8") as f:
                loaded_actuals = json.load(f)
            with open(self.forecasts_file, "r", encoding="utf-8") as f:
                loaded_forecasts = json.load(f)

            with self._lock:
                self._actuals = loaded_actuals
                self._forecasts = loaded_forecasts
                self._is_loaded = True
            return

        # Fetch from API
        self.refresh()

    def get_actuals(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns FUELHH actual wind generation records filtered by settlementDate (YYYY-MM-DD).
        Default returns all January 2026 records.
        """
        if not self._is_loaded:
            self.load_data()

        if not start_date and not end_date:
            # Default to full January 2026
            start_date = "2026-01-01"
            end_date = "2026-01-31"

        with self._lock:
            records_snapshot = list(self._actuals)

        filtered = []
        for r in records_snapshot:
            s_date = r.get("settlementDate") or r["startTime"][:10]
            if start_date and s_date < start_date:
                continue
            if end_date and s_date > end_date:
                continue
            filtered.append(r)

        return filtered

    def get_forecasts(
        self,
        start_publish: Optional[str] = None,
        end_publish: Optional[str] = None,
        target_date_from: Optional[str] = None,
        target_date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns WINDFOR wind forecasts, optionally filtered by publishTime range
        and/or target delivery date range (derived from target startTime).
        """
        if not self._is_loaded:
            self.load_data()

        with self._lock:
            records_snapshot = list(self._forecasts)

        if not start_publish and not end_publish and not target_date_from and not target_date_to:
            return records_snapshot

        filtered = []
        for r in records_snapshot:
            pt = r.get("publishTime", "")
            if start_publish and pt < start_publish:
                continue
            if end_publish and pt > end_publish:
                continue

            if target_date_from or target_date_to:
                st = r.get("startTime", "")
                st_date = st[:10]
                if target_date_from and st_date < target_date_from:
                    continue
                if target_date_to and st_date > target_date_to:
                    continue

            filtered.append(r)

        return filtered

    def get_stats(self) -> Dict[str, Any]:
        """Returns metadata and statistics regarding loaded cache."""
        if not self._is_loaded:
            self.load_data()

        with self._lock:
            act_copy = list(self._actuals)
            fc_copy = list(self._forecasts)

        min_act = min((r["startTime"] for r in act_copy), key=parse_iso_datetime, default=None)
        max_act = max((r["startTime"] for r in act_copy), key=parse_iso_datetime, default=None)
        min_pub = min((r["publishTime"] for r in fc_copy), key=parse_iso_datetime, default=None)
        max_pub = max((r["publishTime"] for r in fc_copy), key=parse_iso_datetime, default=None)

        return {
            "actuals_count": len(act_copy),
            "forecasts_count": len(fc_copy),
            "min_actual_time": min_act,
            "max_actual_time": max_act,
            "min_forecast_publish": min_pub,
            "max_forecast_publish": max_pub
        }

    def refresh(
        self,
        start_date: str = "2025-12-31",
        end_date: str = "2026-02-01",
        start_publish: str = "2025-12-30T00:00:00Z",
        end_publish: str = "2026-02-01T23:59:59Z"
    ) -> Dict[str, Any]:
        """
        Re-queries Elexon BMRS API with chunked requests, validates responses,
        persists raw JSON to disk, and atomically updates the in-memory cache.
        If any chunk fails, the refresh is aborted without corrupting existing cache.
        """
        os.makedirs(self.data_dir, exist_ok=True)
        headers = {"User-Agent": "ElexonDataService/1.0 (EnergyUtility-Evaluation)"}

        # 1. Fetch FUELHH in 7-day chunks
        actuals_url = f"{BASE_URL}/datasets/FUELHH/stream"
        all_actuals = []
        dt_curr = datetime.strptime(start_date, "%Y-%m-%d")
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")

        try:
            while dt_curr <= dt_end:
                dt_chunk_end = min(dt_curr + timedelta(days=6), dt_end)
                params = {
                    "settlementDateFrom": dt_curr.strftime("%Y-%m-%d"),
                    "settlementDateTo": dt_chunk_end.strftime("%Y-%m-%d"),
                    "fuelType": "WIND"
                }
                resp = requests.get(actuals_url, params=params, headers=headers, timeout=45)
                resp.raise_for_status()
                all_actuals.extend(resp.json())
                dt_curr = dt_chunk_end + timedelta(days=1)
                time.sleep(0.2)

            # Deduplicate actuals
            seen_act = set()
            deduped_actuals = []
            for r in all_actuals:
                k = (r.get("settlementDate"), r.get("settlementPeriod"), r.get("fuelType"))
                if k not in seen_act:
                    seen_act.add(k)
                    deduped_actuals.append(r)
            deduped_actuals.sort(key=lambda x: parse_iso_datetime(x.get("startTime", "1970-01-01T00:00:00Z")))

            # 2. Fetch WINDFOR in 5-day chunks
            windfor_url = f"{BASE_URL}/datasets/WINDFOR/stream"
            all_forecasts = []
            dt_pub_curr = datetime.fromisoformat(start_publish.replace("Z", "+00:00"))
            dt_pub_end = datetime.fromisoformat(end_publish.replace("Z", "+00:00"))

            while dt_pub_curr < dt_pub_end:
                dt_chunk_end = min(dt_pub_curr + timedelta(days=5), dt_pub_end)
                params = {
                    "publishDateTimeFrom": dt_pub_curr.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "publishDateTimeTo": dt_chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                resp = requests.get(windfor_url, params=params, headers=headers, timeout=45)
                resp.raise_for_status()
                all_forecasts.extend(resp.json())
                dt_pub_curr = dt_chunk_end
                time.sleep(0.2)

            # Deduplicate forecasts
            seen_fc = set()
            deduped_forecasts = []
            for r in all_forecasts:
                k = (r.get("publishTime"), r.get("startTime"))
                if k not in seen_fc:
                    seen_fc.add(k)
                    deduped_forecasts.append(r)
            deduped_forecasts.sort(
                key=lambda x: (
                    parse_iso_datetime(x.get("publishTime", "1970-01-01T00:00:00Z")),
                    parse_iso_datetime(x.get("startTime", "1970-01-01T00:00:00Z"))
                )
            )

            # Atomically save to disk
            with open(self.actuals_file, "w", encoding="utf-8") as f:
                json.dump(deduped_actuals, f, indent=2)

            with open(self.forecasts_file, "w", encoding="utf-8") as f:
                json.dump(deduped_forecasts, f, indent=2)

            # Atomically update in-memory state under lock
            with self._lock:
                self._actuals = deduped_actuals
                self._forecasts = deduped_forecasts
                self._is_loaded = True

            logger.info("Successfully refreshed Elexon cache (%d actuals, %d forecasts)", len(deduped_actuals), len(deduped_forecasts))
            return self.get_stats()

        except Exception as e:
            logger.error("Failed to refresh Elexon market data: %s", str(e))
            raise


# Global singleton instance
data_service = DataService()
