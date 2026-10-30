import React from 'react';
import { MetricsSummary } from '../types';

interface MetricsCardsProps {
  summary: MetricsSummary;
}

export const MetricsCards: React.FC<MetricsCardsProps> = ({ summary }) => {
  const isOverforecast = summary.bias > 0;

  return (
    <div className="metrics-grid">
      {/* 1. MAE Card */}
      <div className="card metric-card">
        <div className="metric-header">
          <span className="metric-title">MAE (Mean Absolute Error)</span>
          <span className="metric-tag">Volume Delta</span>
        </div>
        <div className="metric-value">
          {summary.mae.toLocaleString(undefined, { maximumFractionDigits: 1 })}{' '}
          <span className="metric-unit">MW</span>
        </div>
        <p className="metric-desc">
          Average magnitude of unhedged power per settlement period requiring intraday balancing.
        </p>
      </div>

      {/* 2. RMSE Card */}
      <div className="card metric-card">
        <div className="metric-header">
          <span className="metric-title">RMSE (Root Mean Square Error)</span>
          <span className="metric-tag warning">Outlier Risk</span>
        </div>
        <div className="metric-value">
          {summary.rmse.toLocaleString(undefined, { maximumFractionDigits: 1 })}{' '}
          <span className="metric-unit">MW</span>
        </div>
        <p className="metric-desc">
          Penalizes severe forecast blunders that risk imbalance cash-out price spikes.
        </p>
      </div>

      {/* 3. Bias Card */}
      <div className={`card metric-card ${isOverforecast ? 'border-warning' : 'border-info'}`}>
        <div className="metric-header">
          <span className="metric-title">Bias (Mean Error)</span>
          <span className={`metric-tag ${isOverforecast ? 'tag-warning' : 'tag-info'}`}>
            {isOverforecast ? 'Over-Forecast (SHORT)' : 'Under-Forecast (LONG)'}
          </span>
        </div>
        <div className="metric-value">
          {summary.bias > 0 ? `+${summary.bias.toLocaleString(undefined, { maximumFractionDigits: 1 })}` : summary.bias.toLocaleString(undefined, { maximumFractionDigits: 1 })}{' '}
          <span className="metric-unit">MW</span>
        </div>
        <p className="metric-desc">
          {isOverforecast
            ? 'Wind persistently under-delivered; trader under-bought thermal power (imbalance deficit).'
            : 'Wind persistently over-delivered; trader over-bought thermal power (imbalance surplus).'}
        </p>
      </div>

      {/* 4. Normalised Error Card */}
      <div className="card metric-card">
        <div className="metric-header">
          <span className="metric-title">Normalised Error (nMAE)</span>
          <span className="metric-tag">Standardized</span>
        </div>
        <div className="metric-value">
          {summary.nmaeCapacity.toFixed(2)}%{' '}
          <span className="metric-unit">of Fleet Capacity</span>
        </div>
        <p className="metric-desc">
          {summary.nmaeMean.toFixed(1)}% of mean generation ({summary.meanActualMW.toLocaleString(undefined, { maximumFractionDigits: 0 })} MW avg outturn).
        </p>
      </div>
    </div>
  );
};
