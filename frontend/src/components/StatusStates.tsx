import React from 'react';

export const LoadingState: React.FC<{ message?: string }> = ({ message = 'Reconciling Elexon BMRS forecasts & actuals...' }) => {
  return (
    <div className="state-container loading-container">
      <div className="spinner"></div>
      <p className="state-message">{message}</p>
      <span className="state-sub">Loading half-hourly settlement periods and calculating metrics</span>
    </div>
  );
};

export const ErrorState: React.FC<{ error: string; onRetry: () => void }> = ({ error, onRetry }) => {
  return (
    <div className="state-container error-container">
      <div className="error-icon">⚠️</div>
      <h3 className="error-title">Unable to Load Market Analytics</h3>
      <p className="state-message">{error}</p>
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        Retry Connection
      </button>
    </div>
  );
};
