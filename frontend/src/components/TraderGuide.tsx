import React from 'react';

export const TraderGuide: React.FC = () => {
  return (
    <div className="card guide-card">
      <div className="guide-header">
        <h3 className="guide-title">📘 Trader's Quick Guide: How to Read & Apply This Dashboard</h3>
        <span className="guide-badge">Desk Reference</span>
      </div>

      <div className="guide-grid">
        <div className="guide-item">
          <h4>1. The Day-Ahead Decision Gate (D-1 09:00 UK Time)</h4>
          <p>
            Wholesale auction bids on EPEX SPOT and Nord Pool close on morning of day <em>D-1</em> (09:20–09:50 UK time).
            This tool strictly evaluates the <strong>latest single forecast run published before your decision cutoff</strong> (typically National Grid's 07:30 UTC model run). It eliminates lookahead bias.
          </p>
        </div>

        <div className="guide-item">
          <h4>2. Interpreting the Bias Direction (System Balance)</h4>
          <p>
            <strong>Positive Bias (+MW, Over-Forecast):</strong> The forecast predicted more wind than actually delivered. As a buyer, you procured too little thermal generation and entered delivery <strong>SHORT</strong>, having to buy replacement power at punitive System Buy Prices (SBP).
          </p>
          <p style={{ marginTop: '0.4rem' }}>
            <strong>Negative Bias (-MW, Under-Forecast):</strong> Wind generated more than predicted. You over-procured thermal power and entered delivery <strong>LONG</strong>, spilling surplus energy at lower System Sell Prices (SSP).
          </p>
        </div>

        <div className="guide-item">
          <h4>3. MAE vs RMSE: Hedging & Risk Margins</h4>
          <p>
            <strong>MAE (Mean Absolute Error):</strong> Represents the expected megawatt volume you will have to adjust and trade in intraday continuous markets to stay balanced.
          </p>
          <p style={{ marginTop: '0.4rem' }}>
            <strong>RMSE (Root Mean Square Error):</strong> Penalizes extreme misses. When RMSE significantly exceeds MAE, expect volatile spikes that require wider spinning reserves and wider cash-out risk buffers.
          </p>
        </div>

        <div className="guide-item">
          <h4>4. Horizon Decay (Lead Time Penalty)</h4>
          <p>
            Forecast lead time spans from <strong>~16 hours</strong> (for SP 1 at 00:00) to <strong>~40 hours</strong> (for SP 48 at 23:30). Error naturally climbs for late evening hours. Use this curve to apply steeper uncertainty discounts to late-day blocks.
          </p>
        </div>
      </div>
    </div>
  );
};
