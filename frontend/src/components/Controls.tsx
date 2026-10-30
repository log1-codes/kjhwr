import React from 'react';

interface ControlsProps {
  startDate: string;
  endDate: string;
  cutoffTime: string;
  isLoading: boolean;
  onStartDateChange: (val: string) => void;
  onEndDateChange: (val: string) => void;
  onCutoffTimeChange: (val: string) => void;
  onApply: () => void;
}

export const Controls: React.FC<ControlsProps> = ({
  startDate,
  endDate,
  cutoffTime,
  isLoading,
  onStartDateChange,
  onEndDateChange,
  onCutoffTimeChange,
  onApply,
}) => {
  const setPreset = (start: string, end: string) => {
    onStartDateChange(start);
    onEndDateChange(end);
  };

  return (
    <div className="card controls-card">
      <div className="controls-row">
        <div className="control-group">
          <label className="control-label" htmlFor="start-date">
            Start Delivery Date
          </label>
          <input
            id="start-date"
            type="date"
            className="input-control"
            value={startDate}
            min="2026-01-01"
            max="2026-01-31"
            onChange={(e) => onStartDateChange(e.target.value)}
          />
        </div>

        <div className="control-group">
          <label className="control-label" htmlFor="end-date">
            End Delivery Date
          </label>
          <input
            id="end-date"
            type="date"
            className="input-control"
            value={endDate}
            min="2026-01-01"
            max="2026-01-31"
            onChange={(e) => onEndDateChange(e.target.value)}
          />
        </div>

        <div className="control-group">
          <label className="control-label" htmlFor="cutoff-time">
            Decision Cutoff (UK Time on D-1)
          </label>
          <select
            id="cutoff-time"
            className="input-control select-control"
            value={cutoffTime}
            onChange={(e) => onCutoffTimeChange(e.target.value)}
          >
            <option value="07:00">07:00 UK Time (Early Desk Preparation)</option>
            <option value="08:00">08:00 UK Time (Pre-Auction Strategy)</option>
            <option value="09:00">09:00 UK Time (Standard Decision Gate)</option>
            <option value="09:30">09:30 UK Time (EPEX Order Book Close)</option>
            <option value="10:00">10:00 UK Time (Post-Auction Intraday)</option>
            <option value="11:00">11:00 UK Time (Late Balancing)</option>
          </select>
        </div>

        <div className="control-group button-group">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onApply}
            disabled={isLoading}
          >
            {isLoading ? 'Updating...' : 'Update Analysis'}
          </button>
        </div>
      </div>

      <div className="presets-row">
        <span className="preset-label">Quick Presets:</span>
        <button
          type="button"
          className={`btn btn-sm ${startDate === '2026-01-01' && endDate === '2026-01-31' ? 'btn-active' : ''}`}
          onClick={() => setPreset('2026-01-01', '2026-01-31')}
        >
          Full January 2026
        </button>
        <button
          type="button"
          className={`btn btn-sm ${startDate === '2026-01-01' && endDate === '2026-01-07' ? 'btn-active' : ''}`}
          onClick={() => setPreset('2026-01-01', '2026-01-07')}
        >
          Week 1 (Jan 1–7)
        </button>
        <button
          type="button"
          className={`btn btn-sm ${startDate === '2026-01-08' && endDate === '2026-01-14' ? 'btn-active' : ''}`}
          onClick={() => setPreset('2026-01-08', '2026-01-14')}
        >
          Week 2 (Jan 8–14)
        </button>
        <button
          type="button"
          className={`btn btn-sm ${startDate === '2026-01-15' && endDate === '2026-01-21' ? 'btn-active' : ''}`}
          onClick={() => setPreset('2026-01-15', '2026-01-21')}
        >
          Week 3 (Jan 15–21)
        </button>
        <button
          type="button"
          className={`btn btn-sm ${startDate === '2026-01-22' && endDate === '2026-01-31' ? 'btn-active' : ''}`}
          onClick={() => setPreset('2026-01-22', '2026-01-31')}
        >
          Week 4+ (Jan 22–31)
        </button>
      </div>
    </div>
  );
};
