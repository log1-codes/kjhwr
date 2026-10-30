import React from 'react';

export const Header: React.FC = () => {
  return (
    <header className="header">
      <div className="header-left">
        <div className="logo-badge">⚡ UK POWER DESK</div>
        <div>
          <h1 className="header-title">Day-Ahead Wind Forecast & Outturn Analytics</h1>
          <p className="header-subtitle">
            Evaluating National Grid ESO forecast accuracy at auction decision gate (January 2026)
          </p>
        </div>
      </div>
      <div className="header-right">
        <div className="market-badge">
          <span className="dot pulse"></span>
          <span>EPEX / NordPool D-1 Benchmark</span>
        </div>
        <div className="tag">Resolution: Half-Hourly (SP 1–48)</div>
      </div>
    </header>
  );
};
