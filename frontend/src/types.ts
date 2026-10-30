export interface AlignedRecord {
  startTime: string;
  settlementDate: string;
  settlementPeriod: number;
  publishTime: string;
  actualGeneration: number;
  forecastGeneration: number;
  error: number;
  absoluteError: number;
  percentageError: number | null;
  horizonHours: number;
}

export interface HorizonMetric {
  horizonBin: string;
  horizonMin: number;
  horizonMax: number;
  sampleCount: number;
  mae: number;
  rmse: number;
  bias: number;
}

export interface MetricsSummary {
  sampleCount: number;
  totalActualEnergyMWh: number;
  totalForecastEnergyMWh: number;
  meanActualMW: number;
  meanForecastMW: number;
  mae: number;
  rmse: number;
  bias: number;
  nmaeCapacity: number;
  nmaeMean: number;
  mapeThresholded: number | null;
  maxOverforecastMW: number;
  maxUnderforecastMW: number;
  p90AbsoluteError: number;
}

export interface MetricsResponse {
  metadata: {
    start_date: string;
    end_date: string;
    cutoff_time: string;
    cutoff_day_offset: number;
    sample_count: number;
  };
  summary: MetricsSummary;
  horizonMetrics?: HorizonMetric[];
  series?: AlignedRecord[];
}
