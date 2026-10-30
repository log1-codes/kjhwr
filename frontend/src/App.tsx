import React, { useState, useEffect, useCallback } from 'react';
import { MetricsResponse } from './types';
import { fetchMetrics } from './api';
import { Header } from './components/Header';
import { Controls } from './components/Controls';
import { MetricsCards } from './components/MetricsCards';
import { TimeSeriesChart } from './components/TimeSeriesChart';
import { HorizonChart } from './components/HorizonChart';
import { TraderGuide } from './components/TraderGuide';
import { LoadingState, ErrorState } from './components/StatusStates';

export const App: React.FC = () => {
  const [startDate, setStartDate] = useState<string>('2026-01-01');
  const [endDate, setEndDate] = useState<string>('2026-01-31');
  const [cutoffTime, setCutoffTime] = useState<string>('09:00');
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchMetrics(startDate, endDate, cutoffTime);
      setData(response);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred while fetching metrics.');
    } finally {
      setIsLoading(false);
    }
  }, [startDate, endDate, cutoffTime]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="app-shell">
      <Header />

      <main className="dashboard-content">
        <Controls
          startDate={startDate}
          endDate={endDate}
          cutoffTime={cutoffTime}
          isLoading={isLoading}
          onStartDateChange={setStartDate}
          onEndDateChange={setEndDate}
          onCutoffTimeChange={setCutoffTime}
          onApply={loadData}
        />

        {isLoading && (
          <LoadingState message={data ? "Recalculating forecast reconciliation..." : undefined} />
        )}

        {error && !isLoading && <ErrorState error={error} onRetry={loadData} />}

        {!isLoading && !error && data && (
          <>
            <MetricsCards summary={data.summary} />

            <div className="charts-stack">
              <TimeSeriesChart series={data.series || []} />
              <HorizonChart metrics={data.horizonMetrics || []} />
            </div>

            <TraderGuide />
          </>
        )}
      </main>

      <footer className="footer">
        <p>
          Data Sources: Elexon BMRS Streams (<code>FUELHH</code> Actuals & <code>WINDFOR</code> Forecasts).
          Evaluated for UK Day-Ahead Power Procurement (January 2026).
        </p>
      </footer>
    </div>
  );
};

export default App;
