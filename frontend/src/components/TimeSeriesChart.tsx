import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { AlignedRecord } from '../types';

interface TimeSeriesChartProps {
  series: AlignedRecord[];
}

export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({ series }) => {
  if (!series || series.length === 0) {
    return (
      <div className="card chart-card empty-chart">
        <p>No settlement periods available for the selected dates.</p>
      </div>
    );
  }

  // Format tick labels on X-axis (e.g. '01 Jan 12:00' or 'Jan 05')
  const formatXAxis = (tickItem: string) => {
    try {
      const d = new Date(tickItem);
      const day = d.getUTCDate().toString().padStart(2, '0');
      const hour = d.getUTCHours().toString().padStart(2, '0');
      const minute = d.getUTCMinutes().toString().padStart(2, '0');
      if (series.length > 200) {
        return hour === '00' && minute === '00' ? `${day} Jan` : '';
      }
      return `${day} Jan ${hour}:${minute}`;
    } catch {
      return tickItem;
    }
  };

  // Custom rich tooltip for power traders
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data: AlignedRecord = payload[0].payload;
      const isOver = data.error > 0;
      return (
        <div className="custom-tooltip">
          <div className="tooltip-header">
            <strong>{data.settlementDate}</strong> (SP {data.settlementPeriod}) — {data.startTime.substring(11, 16)} UTC
          </div>
          <div className="tooltip-row text-actual">
            <span>Actual Outturn:</span>
            <strong>{data.actualGeneration.toLocaleString()} MW</strong>
          </div>
          <div className="tooltip-row text-forecast">
            <span>Day-Ahead Forecast:</span>
            <strong>{data.forecastGeneration.toLocaleString()} MW</strong>
          </div>
          <div className={`tooltip-row ${isOver ? 'text-warning' : 'text-info'}`}>
            <span>Forecast Error:</span>
            <strong>
              {data.error > 0 ? `+${data.error.toLocaleString()}` : data.error.toLocaleString()} MW
              {data.percentageError !== null && ` (${data.percentageError.toFixed(1)}%)`}
            </strong>
          </div>
          <div className="tooltip-footer">
            Run Published: {data.publishTime.substring(0, 16).replace('T', ' ')} UTC ({data.horizonHours}h lead)
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
          <h2 className="chart-title">Day-Ahead Forecast vs Outturn Wind Generation</h2>
          <p className="chart-subtitle">
            Half-hourly National Grid generation outturn (FUELHH) matched against latest WINDFOR run available at decision cutoff
          </p>
        </div>
        <div className="chart-stat-chip">
          {series.length} Settlement Periods ({series.length / 2} Hours)
        </div>
      </div>

      <div className="chart-container" style={{ width: '100%', height: 380 }}>
        <ResponsiveContainer>
          <LineChart data={series} margin={{ top: 10, right: 20, left: 10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
            <XAxis
              dataKey="startTime"
              tickFormatter={formatXAxis}
              stroke="#94a3b8"
              fontSize={11}
              minTickGap={series.length > 500 ? 50 : 25}
            />
            <YAxis
              stroke="#94a3b8"
              fontSize={11}
              tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
              label={{ value: 'Generation (MW)', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 11 }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              align="right"
              wrapperStyle={{ paddingBottom: '10px' }}
            />
            <Line
              type="monotone"
              dataKey="actualGeneration"
              name="Actual Outturn (FUELHH)"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="forecastGeneration"
              name="Day-Ahead Forecast (Cutoff)"
              stroke="#0ea5e9"
              strokeWidth={2}
              strokeDasharray="4 2"
              dot={false}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
