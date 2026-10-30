"""
backend/app/models.py

Pydantic models defining request schemas, response envelopes, and data structures
for the UK Wind Day-Ahead Forecast & Actuals analytics platform.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CacheStats(BaseModel):
    """Metadata regarding currently loaded in-memory Elexon cache."""
    actuals_count: int = Field(..., description="Number of FUELHH actual generation records loaded")
    forecasts_count: int = Field(..., description="Number of WINDFOR forecast records loaded")
    min_actual_time: Optional[str] = Field(None, description="Earliest actual startTime in UTC")
    max_actual_time: Optional[str] = Field(None, description="Latest actual startTime in UTC")
    min_forecast_publish: Optional[str] = Field(None, description="Earliest forecast publishTime in UTC")
    max_forecast_publish: Optional[str] = Field(None, description="Latest forecast publishTime in UTC")


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field("healthy", description="Application health status")
    version: str = Field("1.0.0", description="API version")
    cache: CacheStats = Field(..., description="Underlying cache statistics")


class ActualRecord(BaseModel):
    """Single half-hourly actual wind generation outturn record from FUELHH."""
    startTime: str = Field(..., description="Half-hour start timestamp in UTC (ISO 8601)")
    settlementDate: str = Field(..., description="GB Settlement Date (YYYY-MM-DD)")
    settlementPeriod: int = Field(..., description="GB Settlement Period (1 to 48)")
    fuelType: str = Field("WIND", description="Fuel type category")
    generation: float = Field(..., description="Average power generated over the half-hour in MW")


class ActualsResponse(BaseModel):
    """Response envelope for outturn actual wind generation."""
    metadata: Dict[str, Any] = Field(..., description="Query parameters and result summary")
    data: List[ActualRecord] = Field(..., description="List of actual generation records")


class ForecastRecord(BaseModel):
    """Single day-ahead forecast record selected at decision cutoff."""
    startTime: str = Field(..., description="Target delivery start timestamp in UTC (ISO 8601)")
    settlementDate: str = Field(..., description="Target GB Settlement Date (YYYY-MM-DD)")
    settlementPeriod: int = Field(..., description="Target GB Settlement Period (1 to 48)")
    publishTime: str = Field(..., description="Timestamp when the forecast was published in UTC")
    generation: float = Field(..., description="Forecasted average wind power in MW")
    horizonHours: float = Field(..., description="Lead-time horizon in hours (startTime - publishTime)")


class ForecastsResponse(BaseModel):
    """Response envelope for latest wind forecasts at cutoff."""
    metadata: Dict[str, Any] = Field(..., description="Cutoff configuration and record count")
    data: List[ForecastRecord] = Field(..., description="Selected forecast records at cutoff")


class AlignedRecord(BaseModel):
    """Merged record aligning half-hourly actual outturn with decision-cutoff forecast."""
    startTime: str = Field(..., description="Target delivery start timestamp in UTC (ISO 8601)")
    settlementDate: str = Field(..., description="Target GB Settlement Date (YYYY-MM-DD)")
    settlementPeriod: int = Field(..., description="Target GB Settlement Period (1 to 48)")
    publishTime: str = Field(..., description="Matched forecast publish timestamp in UTC")
    actualGeneration: float = Field(..., description="Actual wind outturn in MW")
    forecastGeneration: float = Field(..., description="Forecasted wind generation in MW")
    error: float = Field(..., description="Forecast minus Actual in MW (positive = over-forecast / short)")
    absoluteError: float = Field(..., description="Absolute forecast deviation in MW")
    percentageError: Optional[float] = Field(None, description="Percentage error (|err| / actual * 100), filtered for actual >= 100 MW")
    horizonHours: float = Field(..., description="Lead time in hours between publication and delivery")


class HorizonMetric(BaseModel):
    """Summary error metrics binned by forecast lead-time horizon."""
    horizonBin: str = Field(..., description="Label for horizon bin (e.g. '16-20h')")
    horizonMin: float = Field(..., description="Lower horizon bound in hours")
    horizonMax: float = Field(..., description="Upper horizon bound in hours")
    sampleCount: int = Field(..., description="Number of settlement periods in this bin")
    mae: float = Field(..., description="Mean Absolute Error in MW")
    rmse: float = Field(..., description="Root Mean Square Error in MW")
    bias: float = Field(..., description="Mean forecast error in MW")


class MetricsSummary(BaseModel):
    """Overall quantitative performance indicators for power buyers."""
    sampleCount: int = Field(..., description="Total evaluated half-hour settlement periods")
    totalActualEnergyMWh: float = Field(..., description="Total actual wind energy (sum(MW * 0.5h)) in MWh")
    totalForecastEnergyMWh: float = Field(..., description="Total forecasted wind energy (sum(MW * 0.5h)) in MWh")
    meanActualMW: float = Field(..., description="Average actual wind power in MW")
    meanForecastMW: float = Field(..., description="Average forecasted wind power in MW")
    mae: float = Field(..., description="Mean Absolute Error in MW")
    rmse: float = Field(..., description="Root Mean Square Error in MW")
    bias: float = Field(..., description="Mean error (Forecast - Actual) in MW (positive = over-forecast / short)")
    nmaeCapacity: float = Field(..., description="Normalized MAE against UK installed wind capacity (~30.5 GW) in %")
    nmaeMean: float = Field(..., description="Normalized MAE against sample mean actual generation in %")
    mapeThresholded: Optional[float] = Field(None, description="Mean Absolute Percentage Error for periods >= 100 MW in %")
    maxOverforecastMW: float = Field(..., description="Maximum over-forecast error (MW) leaving buyer short")
    maxUnderforecastMW: float = Field(..., description="Maximum under-forecast error (MW) leaving buyer long")
    p90AbsoluteError: float = Field(..., description="90th percentile of absolute error in MW")


class MetricsResponse(BaseModel):
    """Response envelope for quantitative evaluation metrics."""
    metadata: Dict[str, Any] = Field(..., description="Query filters and date range")
    summary: MetricsSummary = Field(..., description="Aggregated KPI metrics")
    horizonMetrics: Optional[List[HorizonMetric]] = Field(None, description="Error metrics broken down by lead-time horizon")
    series: Optional[List[AlignedRecord]] = Field(None, description="Full aligned time-series if requested")
