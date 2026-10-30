import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { HorizonMetric } from '../types';

interface HorizonChartProps {
  metrics: HorizonMetric[];
}

export const HorizonChart: React.FC<HorizonChartProps> = ({ metrics }) => {
  if (!metrics || metrics.length === 0) {
    return (
      <div className="card chart-card empty-chart">
        <p>No horizon metrics available for the current selection.</p>
      </div>
    );
  }

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data: HorizonMetric = payload[0].payload;
      return (
        <div className="custom-tooltip">
          <div className="tooltip-header">
            <strong>Horizon: {data.horizonBin}</strong> ({data.sampleCount} half-hours)
          </div>
          <div className="tooltip-row text-mae">
            <span>MAE:</span>
            <strong>{data.mae.toLocaleString()} MW</strong>
          </div>
          <div className="tooltip-row text-rmse">
            <span>RMSE:</span>
            <strong>{data.rmse.toLocaleString()} MW</strong>
          </div>
          <div className="tooltip-row">
            <span>Bias:</span>
            <strong>{data.bias > 0 ? `+${data.bias.toLocaleString()}` : data.bias.toLocaleString()} MW</strong>
          </div>
          <div className="tooltip-footer">
            Hours elapsed between forecast publication and physical power delivery.
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <div>
          <h2 className="chart-title">Error by Forecast Horizon (Lead Time)</h2>
          <p className="chart-subtitle">
            Forecast degradation as lead time increases from morning SPs (~16h) to late-night SPs (~40h)
          </p>
        </div>
        <div className="chart-stat-chip">
          {metrics.length} Horizon Bins
        </div>
      </div>

      <div className="chart-container" style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={metrics} margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis
              dataKey="horizonBin"
              stroke="#94a3b8"
              fontSize={11}
              label={{ value: 'Lead Time Horizon (Hours from Publication to Delivery)', position: 'insideBottom', offset: -10, fill: '#94a3b8', fontSize: 11 }}
            />
            <YAxis
              stroke="#94a3b8"
              fontSize={11}
              tickFormatter={(val) => `${(val / 1000).toFixed(1)}k`}
              label={{ value: 'Forecast Error (MW)', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 11 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              align="right"
              wrapperStyle={{ paddingBottom: '10px' }}
            />
            <Bar
              dataKey="mae"
              name="MAE (Volume Risk, MW)"
              fill="#0ea5e9"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="rmse"
              name="RMSE (Extreme Risk, MW)"
              fill="#f59e0b"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
