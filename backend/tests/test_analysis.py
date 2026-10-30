"""
backend/tests/test_analysis.py

Comprehensive unit tests for pure domain logic in backend/app/analysis.py.

Coverage:
- Cutoff selection: latest forecast at-or-before cutoff, post-cutoff exclusion,
  coherent-run preference, point-by-point fallback, exact-boundary inclusion.
- Temporal alignment: half-hourly step forward-fill, missing forecast → dropped actual.
- DST boundary: get_cutoff_timestamp treats cutoff as raw UTC, which is incorrect
  during BST (documented behaviour test).
- Metric formulas: MAE, RMSE, bias, nMAE (capacity & mean), thresholded MAPE,
  energy (MWh = MW × 0.5h), P90, max over/under — all hand-calculated.
- Horizon binning: bin assignment, per-bin MAE/RMSE/bias.
- Edge cases: empty inputs, single record, all-below-threshold MAPE, zero capacity.
"""

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.analysis import (
    parse_iso_datetime,
    get_cutoff_timestamp,
    select_latest_forecast_at_cutoff,
    join_forecasts_with_actuals,
    calculate_error_metrics,
    group_metrics_by_horizon,
)


# ---------------------------------------------------------------------------
# Helpers to build small synthetic datasets
# ---------------------------------------------------------------------------

def _fc(publish: str, start: str, gen: float) -> dict:
    """Shorthand to build one WINDFOR-shaped forecast record."""
    return {"publishTime": publish, "startTime": start, "generation": gen}


def _act(start: str, gen: float, sd: str | None = None, sp: int = 1) -> dict:
    """Shorthand to build one FUELHH-shaped actual record."""
    return {
        "startTime": start,
        "settlementDate": sd or start[:10],
        "settlementPeriod": sp,
        "fuelType": "WIND",
        "generation": gen,
    }


def _make_full_run(publish: str, day: str, base_gen: float = 10000.0) -> list[dict]:
    """Creates a complete 24-hour forecast run (one point per hour) for a given day."""
    return [
        _fc(publish, f"{day}T{h:02d}:00:00Z", base_gen + h * 10)
        for h in range(24)
    ]


# ===========================================================================
# 1. parse_iso_datetime
# ===========================================================================

class TestParseIsoDatetime:
    def test_z_suffix(self):
        dt = parse_iso_datetime("2026-01-15T13:45:00Z")
        assert dt == datetime(2026, 1, 15, 13, 45, tzinfo=timezone.utc)

    def test_offset_suffix(self):
        dt = parse_iso_datetime("2026-07-01T10:00:00+01:00")
        # +01:00 → 09:00 UTC
        assert dt == datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)

    def test_always_returns_utc(self):
        dt = parse_iso_datetime("2026-03-29T01:30:00Z")
        assert dt.tzinfo == timezone.utc


# ===========================================================================
# 2. get_cutoff_timestamp
# ===========================================================================

class TestGetCutoffTimestamp:
    def test_standard_january_d_minus_1(self):
        """January is GMT → 09:00 UK = 09:00 UTC."""
        cutoff = get_cutoff_timestamp(date(2026, 1, 15), "09:00", day_offset=1)
        assert cutoff == datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)

    def test_custom_cutoff_time(self):
        cutoff = get_cutoff_timestamp(date(2026, 1, 5), "11:30", day_offset=1)
        assert cutoff == datetime(2026, 1, 4, 11, 30, tzinfo=timezone.utc)

    def test_day_offset_2(self):
        cutoff = get_cutoff_timestamp(date(2026, 1, 10), "09:00", day_offset=2)
        assert cutoff == datetime(2026, 1, 8, 9, 0, tzinfo=timezone.utc)

    def test_dst_boundary_spring_bst(self):
        """
        On 2026-03-29 UK clocks spring forward (GMT -> BST).
        For delivery on 2026-03-30, D-1 is 2026-03-29.
        09:00 UK local on 2026-03-29 (BST) = 08:00 UTC.
        With ZoneInfo('Europe/London'), this correctly yields 08:00 UTC.
        """
        cutoff = get_cutoff_timestamp(date(2026, 3, 30), "09:00", day_offset=1)
        assert cutoff == datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)

    def test_summer_bst_conversion(self):
        """During summer (July), 09:00 BST = 08:00 UTC."""
        cutoff = get_cutoff_timestamp(date(2026, 7, 10), "09:00", day_offset=1)
        assert cutoff == datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)

    def test_invalid_cutoff_time_format_raises_error(self):
        """Malformed cutoff strings must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid cutoff time format"):
            get_cutoff_timestamp(date(2026, 1, 15), "invalid")
        with pytest.raises(ValueError, match="Invalid cutoff time format"):
            get_cutoff_timestamp(date(2026, 1, 15), "9:0")

    def test_invalid_cutoff_time_range_raises_error(self):
        """Out of range hours/minutes must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid cutoff time values"):
            get_cutoff_timestamp(date(2026, 1, 15), "24:00")
        with pytest.raises(ValueError, match="Invalid cutoff time values"):
            get_cutoff_timestamp(date(2026, 1, 15), "12:60")


# ===========================================================================
# 3. select_latest_forecast_at_cutoff
# ===========================================================================

class TestSelectLatestForecastAtCutoff:

    def test_picks_latest_eligible_run(self):
        """Three runs for the same target hour; only the two before cutoff are eligible."""
        forecasts = [
            _fc("2026-01-01T02:30:00Z", "2026-01-02T12:00:00Z", 8000),
            _fc("2026-01-01T07:30:00Z", "2026-01-02T12:00:00Z", 9500),  # ← latest eligible
            _fc("2026-01-01T11:30:00Z", "2026-01-02T12:00:00Z", 11000),  # after cutoff
        ]
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        chosen = sel["2026-01-02T12:00:00Z"]
        assert chosen["publishTime"] == "2026-01-01T07:30:00Z"
        assert chosen["generation"] == 9500

    def test_post_cutoff_forecast_excluded(self):
        """A forecast published after cutoff must never appear in results."""
        forecasts = [
            _fc("2026-01-01T10:00:00Z", "2026-01-02T06:00:00Z", 5000),  # after 09:00
        ]
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        assert "2026-01-02T06:00:00Z" not in sel

    def test_exact_cutoff_boundary_included(self):
        """A forecast published at exactly T_cutoff is <= cutoff and must be included."""
        forecasts = [
            _fc("2026-01-01T09:00:00Z", "2026-01-02T00:00:00Z", 7777),
        ]
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        assert "2026-01-02T00:00:00Z" in sel
        assert sel["2026-01-02T00:00:00Z"]["generation"] == 7777

    def test_coherent_run_preferred_over_partial_newer_run(self):
        """
        If a complete 24-hour run exists at 04:30 and a partial 12-hour run
        exists at 07:30, the algorithm should select the complete 04:30 run
        to avoid Frankenstein ramp jumps.
        """
        complete_run = _make_full_run("2026-01-04T04:30:00Z", "2026-01-05", base_gen=10000)
        # Partial run covering only hours 0-11
        partial_run = [
            _fc("2026-01-04T07:30:00Z", f"2026-01-05T{h:02d}:00:00Z", 15000 + h * 10)
            for h in range(12)
        ]
        forecasts = complete_run + partial_run
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)

        # All 24 hours should come from the 04:30 complete run
        for h in range(24):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert key in sel, f"Missing hour {h}"
            assert sel[key]["publishTime"] == "2026-01-04T04:30:00Z"

    def test_later_complete_run_beats_earlier_complete_run(self):
        """When two complete runs both exist before cutoff, pick the later one."""
        early_run = _make_full_run("2026-01-04T02:30:00Z", "2026-01-05", base_gen=8000)
        late_run = _make_full_run("2026-01-04T07:30:00Z", "2026-01-05", base_gen=12000)
        forecasts = early_run + late_run

        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        for h in range(24):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert sel[key]["publishTime"] == "2026-01-04T07:30:00Z"

    def test_fallback_point_by_point_when_no_complete_run(self):
        """
        When no single run covers all 24 hours, fall back to picking the
        latest eligible forecast per individual target hour.
        """
        # Run A at 02:30 covers hours 0–11 only
        run_a = [_fc("2026-01-04T02:30:00Z", f"2026-01-05T{h:02d}:00:00Z", 6000) for h in range(12)]
        # Run B at 04:30 covers hours 6–17 only
        run_b = [_fc("2026-01-04T04:30:00Z", f"2026-01-05T{h:02d}:00:00Z", 7000) for h in range(6, 18)]

        forecasts = run_a + run_b
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)

        # Hours 0–5: only run A available → 02:30
        for h in range(6):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert sel[key]["publishTime"] == "2026-01-04T02:30:00Z"

        # Hours 6–11: both runs available → pick later (04:30)
        for h in range(6, 12):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert sel[key]["publishTime"] == "2026-01-04T04:30:00Z"

        # Hours 12–17: only run B available → 04:30
        for h in range(12, 18):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert sel[key]["publishTime"] == "2026-01-04T04:30:00Z"

        # Hours 18–23: no data at all
        for h in range(18, 24):
            key = f"2026-01-05T{h:02d}:00:00Z"
            assert key not in sel

    def test_no_eligible_forecasts_returns_empty(self):
        """If all forecasts are after cutoff, result must be empty."""
        forecasts = [
            _fc("2026-01-01T12:00:00Z", "2026-01-02T10:00:00Z", 5000),
            _fc("2026-01-01T15:00:00Z", "2026-01-02T10:00:00Z", 6000),
        ]
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        assert len(sel) == 0

    def test_empty_input(self):
        assert select_latest_forecast_at_cutoff([], "09:00", 1) == {}


# ===========================================================================
# 4. join_forecasts_with_actuals
# ===========================================================================

class TestJoinForecastsWithActuals:

    def test_half_hourly_step_forward_fill(self):
        """Both :00 and :30 actuals for the same hour match a single hourly forecast."""
        actuals = [
            _act("2026-01-05T14:00:00Z", 9000, sp=29),
            _act("2026-01-05T14:30:00Z", 9200, sp=30),
        ]
        forecasts = {
            "2026-01-05T14:00:00Z": _fc("2026-01-04T07:30:00Z", "2026-01-05T14:00:00Z", 10000),
        }
        aligned = join_forecasts_with_actuals(actuals, forecasts)
        assert len(aligned) == 2

        # SP 29 (14:00)
        assert aligned[0]["actualGeneration"] == 9000
        assert aligned[0]["forecastGeneration"] == 10000
        assert aligned[0]["error"] == 1000       # over-forecast
        assert aligned[0]["absoluteError"] == 1000
        assert aligned[0]["percentageError"] == pytest.approx(11.11, abs=0.01)
        # horizon: 2026-01-05 14:00 − 2026-01-04 07:30 = 30.5 hours
        assert aligned[0]["horizonHours"] == 30.5

        # SP 30 (14:30) inherits the same hourly forecast
        assert aligned[1]["actualGeneration"] == 9200
        assert aligned[1]["forecastGeneration"] == 10000
        assert aligned[1]["error"] == 800
        # horizon: 2026-01-05 14:30 − 2026-01-04 07:30 = 31.0 hours
        assert aligned[1]["horizonHours"] == 31.0

    def test_missing_forecast_drops_actual(self):
        """
        If no forecast exists for the hour key, the actual is silently dropped.
        This verifies that missing forecasts do not cause errors and that
        the output only contains periods with both actual and forecast data.
        """
        actuals = [
            _act("2026-01-05T03:00:00Z", 4000, sp=7),  # hour 03 has forecast
            _act("2026-01-05T03:30:00Z", 4100, sp=8),   # hour 03 has forecast
            _act("2026-01-05T04:00:00Z", 4200, sp=9),   # hour 04 — NO forecast
            _act("2026-01-05T04:30:00Z", 4300, sp=10),   # hour 04 — NO forecast
        ]
        forecasts = {
            "2026-01-05T03:00:00Z": _fc("2026-01-04T07:30:00Z", "2026-01-05T03:00:00Z", 5000),
            # hour 04 deliberately missing
        }
        aligned = join_forecasts_with_actuals(actuals, forecasts)
        assert len(aligned) == 2  # only SPs 7 and 8
        assert all(r["startTime"].startswith("2026-01-05T03:") for r in aligned)

    def test_percentage_error_none_below_threshold(self):
        """Actuals below 100 MW must have percentageError = None."""
        actuals = [_act("2026-01-05T00:00:00Z", 50, sp=1)]
        forecasts = {
            "2026-01-05T00:00:00Z": _fc("2026-01-04T07:30:00Z", "2026-01-05T00:00:00Z", 100),
        }
        aligned = join_forecasts_with_actuals(actuals, forecasts)
        assert len(aligned) == 1
        assert aligned[0]["error"] == 50       # 100 − 50
        assert aligned[0]["percentageError"] is None

    def test_negative_error_underforecast(self):
        """When actual > forecast, error should be negative (under-forecast / buyer long)."""
        actuals = [_act("2026-01-05T10:00:00Z", 12000, sp=21)]
        forecasts = {
            "2026-01-05T10:00:00Z": _fc("2026-01-04T07:30:00Z", "2026-01-05T10:00:00Z", 8000),
        }
        aligned = join_forecasts_with_actuals(actuals, forecasts)
        assert aligned[0]["error"] == -4000

    def test_empty_actuals(self):
        assert join_forecasts_with_actuals([], {"k": {}}) == []

    def test_empty_forecasts(self):
        actuals = [_act("2026-01-05T00:00:00Z", 5000, sp=1)]
        assert join_forecasts_with_actuals(actuals, {}) == []


# ===========================================================================
# 5. calculate_error_metrics — hand-calculated against 4 synthetic records
# ===========================================================================

class TestCalculateErrorMetrics:
    """
    Synthetic dataset (4 half-hour settlement periods):

        Record  Actual(MW) Forecast(MW)  Error   |Error| %Error
        ------  ---------- ------------ ------   ------- ------
        A       1000       1200          +200     200     20.00%
        B       2000       1500          -500     500     25.00%
        C       3000       3300          +300     300     10.00%
        D         50        100          +50       50     (None, actual < 100)

    Hand-computed metrics:
        n = 4
        MAE             = (200 + 500 + 300 + 50) / 4 = 262.50 MW
        RMSE            = sqrt((200² + 500² + 300² + 50²) / 4)
                        = sqrt((40000 + 250000 + 90000 + 2500) / 4)
                        = sqrt(95625) ≈ 309.23 MW
        Bias            = (200 + (-500) + 300 + 50) / 4 = 12.50 MW
        meanActual      = 6050 / 4 = 1512.50 MW
        meanForecast    = 6100 / 4 = 1525.00 MW
        nMAE_capacity   = 262.5 / 10000 * 100 = 2.625 → rounded 2.62%
        nMAE_mean       = 262.5 / 1512.5 * 100 ≈ 17.36%
        MAPE (>=100 MW) = (20.0 + 25.0 + 10.0) / 3 ≈ 18.33%
        Energy_actual   = 6050 * 0.5 = 3025.0 MWh
        Energy_forecast = 6100 * 0.5 = 3050.0 MWh
        maxOverforecast = max(200, -500, 300, 50) = 300
        maxUnderforecast= min(200, -500, 300, 50) = -500
        P90: sorted |e| = [50, 200, 300, 500]
             idx = ceil(0.9 * 4) - 1 = 3 → 500
    """

    @pytest.fixture()
    def records(self):
        return [
            {"actualGeneration": 1000, "forecastGeneration": 1200, "error": 200,
             "absoluteError": 200, "percentageError": 20.0},
            {"actualGeneration": 2000, "forecastGeneration": 1500, "error": -500,
             "absoluteError": 500, "percentageError": 25.0},
            {"actualGeneration": 3000, "forecastGeneration": 3300, "error": 300,
             "absoluteError": 300, "percentageError": 10.0},
            {"actualGeneration": 50, "forecastGeneration": 100, "error": 50,
             "absoluteError": 50, "percentageError": None},
        ]

    def test_sample_count(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["sampleCount"] == 4

    def test_mae(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["mae"] == 262.5

    def test_rmse(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        expected_rmse = math.sqrt(95625)  # 309.2329…
        assert m["rmse"] == pytest.approx(expected_rmse, abs=0.01)

    def test_bias(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["bias"] == 12.5

    def test_nmae_capacity(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        # 262.5 / 10000 * 100 = 2.625 → rounded to 2 dp = 2.62
        assert m["nmaeCapacity"] == pytest.approx(2.62, abs=0.01)

    def test_nmae_mean(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        # 262.5 / 1512.5 * 100 ≈ 17.355… → rounded 17.36
        assert m["nmaeMean"] == pytest.approx(17.36, abs=0.01)

    def test_mape_thresholded_excludes_sub_100mw(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        # Only records A, B, C (actual ≥ 100): (20 + 25 + 10) / 3 = 18.33
        assert m["mapeThresholded"] == pytest.approx(18.33, abs=0.01)

    def test_energy_mwh_half_hourly_scaling(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        # sum(actual_MW) * 0.5 = (1000 + 2000 + 3000 + 50) * 0.5 = 3025.0
        assert m["totalActualEnergyMWh"] == 3025.0
        # sum(forecast_MW) * 0.5 = (1200 + 1500 + 3300 + 100) * 0.5 = 3050.0
        assert m["totalForecastEnergyMWh"] == 3050.0

    def test_max_overforecast(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["maxOverforecastMW"] == 300

    def test_max_underforecast(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["maxUnderforecastMW"] == -500

    def test_p90(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        # sorted |e| = [50, 200, 300, 500], idx = ceil(3.6)-1 = 3 → 500
        assert m["p90AbsoluteError"] == 500

    def test_mean_actual_and_forecast(self, records):
        m = calculate_error_metrics(records, installed_capacity_mw=10000)
        assert m["meanActualMW"] == 1512.5
        assert m["meanForecastMW"] == 1525.0


class TestCalculateErrorMetricsEdgeCases:

    def test_empty_records(self):
        m = calculate_error_metrics([])
        assert m["sampleCount"] == 0
        assert m["mae"] == 0.0
        assert m["mapeThresholded"] is None

    def test_single_record(self):
        recs = [{"actualGeneration": 5000, "forecastGeneration": 6000,
                 "error": 1000, "absoluteError": 1000, "percentageError": 20.0}]
        m = calculate_error_metrics(recs, installed_capacity_mw=30500)
        assert m["sampleCount"] == 1
        assert m["mae"] == 1000
        assert m["rmse"] == 1000
        assert m["bias"] == 1000
        assert m["p90AbsoluteError"] == 1000

    def test_all_below_mape_threshold(self):
        """If every actual < 100 MW, thresholded MAPE is None."""
        recs = [{"actualGeneration": 50, "forecastGeneration": 80,
                 "error": 30, "absoluteError": 30, "percentageError": None}]
        m = calculate_error_metrics(recs, installed_capacity_mw=10000)
        assert m["mapeThresholded"] is None

    def test_perfect_forecast(self):
        recs = [{"actualGeneration": 7000, "forecastGeneration": 7000,
                 "error": 0, "absoluteError": 0, "percentageError": 0.0}]
        m = calculate_error_metrics(recs)
        assert m["mae"] == 0.0
        assert m["rmse"] == 0.0
        assert m["bias"] == 0.0


# ===========================================================================
# 6. group_metrics_by_horizon
# ===========================================================================

class TestGroupMetricsByHorizon:

    def test_two_bins(self):
        """
        Records at 17h, 19h, 23h with 4h bins:
        Bin 16-20h: records at 17h (+200) and 19h (-100)
        Bin 20-24h: record at 23h (+500)

        Bin 16-20h hand-calc:
            MAE  = (200 + 100) / 2 = 150
            RMSE = sqrt((200² + 100²) / 2) = sqrt(25000) ≈ 158.11
            Bias = (200 + (-100)) / 2 = 50
        Bin 20-24h hand-calc:
            MAE = RMSE = Bias = 500
        """
        records = [
            {"horizonHours": 17.0, "error": 200, "absoluteError": 200},
            {"horizonHours": 19.0, "error": -100, "absoluteError": 100},
            {"horizonHours": 23.0, "error": 500, "absoluteError": 500},
        ]
        bins = group_metrics_by_horizon(records, bin_hours=4.0)
        assert len(bins) == 2

        b1 = bins[0]
        assert b1["horizonBin"] == "16-20h"
        assert b1["sampleCount"] == 2
        assert b1["mae"] == 150.0
        assert b1["bias"] == 50.0
        assert b1["rmse"] == pytest.approx(math.sqrt(25000), abs=0.01)

        b2 = bins[1]
        assert b2["horizonBin"] == "20-24h"
        assert b2["sampleCount"] == 1
        assert b2["mae"] == 500.0
        assert b2["rmse"] == 500.0
        assert b2["bias"] == 500.0

    def test_empty_input(self):
        assert group_metrics_by_horizon([]) == []

    def test_single_record_single_bin(self):
        records = [{"horizonHours": 25.0, "error": -300, "absoluteError": 300}]
        bins = group_metrics_by_horizon(records, bin_hours=4.0)
        assert len(bins) == 1
        assert bins[0]["sampleCount"] == 1
        assert bins[0]["mae"] == 300.0


# ===========================================================================
# 7. End-to-end integration: select → join → metrics
# ===========================================================================

class TestEndToEndPipeline:
    """
    Builds a minimal but realistic synthetic scenario:
    - Delivery day: 2026-01-10
    - Two WINDFOR runs before 09:00 cutoff (04:30 and 07:30), one after (11:30)
    - The 07:30 run is complete (24 hours) → selected
    - FUELHH actuals for hours 00-02 (6 half-hour periods)
    - Verifies the full pipeline produces correct aligned output and metrics.
    """

    @pytest.fixture()
    def actuals(self):
        return [
            _act("2026-01-10T00:00:00Z", 10000, sd="2026-01-10", sp=1),
            _act("2026-01-10T00:30:00Z", 10200, sd="2026-01-10", sp=2),
            _act("2026-01-10T01:00:00Z", 10500, sd="2026-01-10", sp=3),
            _act("2026-01-10T01:30:00Z", 10800, sd="2026-01-10", sp=4),
            _act("2026-01-10T02:00:00Z", 11000, sd="2026-01-10", sp=5),
            _act("2026-01-10T02:30:00Z", 11300, sd="2026-01-10", sp=6),
        ]

    @pytest.fixture()
    def forecasts(self):
        # Complete 07:30 run (should be selected)
        run_0730 = _make_full_run("2026-01-09T07:30:00Z", "2026-01-10", base_gen=11000)
        # Complete 04:30 run (older, should be passed over)
        run_0430 = _make_full_run("2026-01-09T04:30:00Z", "2026-01-10", base_gen=9000)
        # Complete 11:30 run (after cutoff, excluded)
        run_1130 = _make_full_run("2026-01-09T11:30:00Z", "2026-01-10", base_gen=13000)
        return run_0430 + run_0730 + run_1130

    def test_selection_picks_0730_run(self, forecasts):
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        # Spot-check hour 0
        assert sel["2026-01-10T00:00:00Z"]["publishTime"] == "2026-01-09T07:30:00Z"
        # 11:30 run must not appear
        for rec in sel.values():
            assert rec["publishTime"] != "2026-01-09T11:30:00Z"

    def test_pipeline_aligned_count(self, actuals, forecasts):
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        aligned = join_forecasts_with_actuals(actuals, sel)
        assert len(aligned) == 6  # all 6 actuals match (3 hourly forecasts cover them)

    def test_pipeline_metrics(self, actuals, forecasts):
        sel = select_latest_forecast_at_cutoff(forecasts, "09:00", 1)
        aligned = join_forecasts_with_actuals(actuals, sel)
        m = calculate_error_metrics(aligned, installed_capacity_mw=30500)

        assert m["sampleCount"] == 6
        # Quick sanity: 07:30 run has gen=11000+h*10 for hour h,
        # so hour 0 forecast = 11000, hour 1 = 11010, hour 2 = 11020.
        # Actuals: 10000, 10200, 10500, 10800, 11000, 11300.
        # Errors: +1000, +800, +510, +210, +20, -280
        errors = [1000, 800, 510, 210, 20, -280]
        abs_errors = [abs(e) for e in errors]
        expected_mae = sum(abs_errors) / 6
        expected_bias = sum(errors) / 6
        expected_rmse = math.sqrt(sum(e ** 2 for e in errors) / 6)

        assert m["mae"] == pytest.approx(expected_mae, abs=0.01)
        assert m["bias"] == pytest.approx(expected_bias, abs=0.01)
        assert m["rmse"] == pytest.approx(expected_rmse, abs=0.01)
        # Bias is positive → systematic over-forecast in this window
        assert m["bias"] > 0
