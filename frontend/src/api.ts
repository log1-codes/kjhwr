import { MetricsResponse } from './types';

export async function fetchMetrics(
  startDate: string,
  endDate: string,
  cutoffTime: string = '09:00'
): Promise<MetricsResponse> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    cutoff_time: cutoffTime,
    include_horizon: 'true',
    include_series: 'true',
  });

  const apiBase = import.meta.env.VITE_API_BASE_URL || '';
  const response = await fetch(`${apiBase}/api/metrics?${params.toString()}`);
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message = errorBody.detail || `Server returned status ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}
