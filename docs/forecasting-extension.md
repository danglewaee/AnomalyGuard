# Forecasting Extension

AnomalyGuard now includes a deep-learning-forward forecasting prototype that reframes the original monitoring system from reactive anomaly detection into early-warning risk forecasting.

The extension includes a real optional PyTorch LSTM path, while still keeping simpler models as scientific controls. This lets the project communicate a deep learning direction without pretending that model complexity alone earns trust.

## Current Scope

- Input signals: `pH`, `TDS`, `turbidity`, `temperature`, `DO`, and `flow`
- Forecast horizons: default `6h`, `12h`, and `24h`
- Methods:
  - `persistence`: future value equals latest value
  - `moving_average`: future value equals recent window mean
  - `lag_linear`: a lightweight linear lag model over recent multivariate windows
  - `lstm`: trains a compact station-level LSTM in memory when PyTorch and enough readings are available
  - `auto`: prefers `lstm` when available, then falls back to `lag_linear` or simpler baselines
- Output:
  - predicted signal values
  - signal-level risk levels
  - overall station risk level
  - confidence estimate
  - limitations and deep-learning next steps

## Why Deep Learning

Water quality is a multivariate time-series problem. Signals such as turbidity, pH, dissolved oxygen, and flow can change with delayed effects after rainfall, upstream discharge, tidal shifts, or operational changes. LSTM-style sequence models are useful because they can preserve information over previous time steps and learn temporal precursors before a fixed threshold is crossed.

## Why Keep Baselines

Baselines are not a retreat from deep learning. They are the control group that proves whether a deep model is adding value. A public-interest warning system should show that a deep model improves:

- Value accuracy: `MAE`, `RMSE`
- Warning utility: precision, recall, false alarm rate, and lead time
- Operational trust: whether alerts are stable enough for operators or local authorities to act on

## Enable LSTM Runtime

The default backend install keeps PyTorch optional to avoid making every deployment heavy. To enable the LSTM path:

```powershell
cd backend
python -m pip install -r requirements-dl.txt
```

Then request:

```powershell
curl "http://localhost:8000/api/forecasts/water-quality?station_id=mekong-can-tho&horizon_hours=6&horizon_hours=12&method=lstm"
```

If PyTorch is not installed or there is not enough station history, the endpoint returns a baseline fallback with an explicit warning instead of failing.

## Interview Framing

Use this wording when explaining the project:

> The original project detected water-quality anomalies from sensor readings. The forecasting extension asks a more useful question: can we estimate risk before the water becomes unsafe? I added a station-level LSTM forecasting path because water quality has temporal dependencies across pH, turbidity, dissolved oxygen, and flow. In a richer deployment with multiple stations, I would extend this toward spatiotemporal models such as ConvLSTM or attention-based architectures. I still keep persistence and lag-linear baselines because they define the bar a deep model must beat before it should be trusted in a public-interest setting.

## Deep Learning Roadmap

- Collect longer calibrated station-level time series.
- Add weather, tide, rainfall, upstream discharge, and seasonal context.
- Train LSTM, ConvLSTM, Informer, or LTSF-style model candidates as versioned artifacts.
- Compare every deep model against persistence, moving average, and lag-linear baselines.
- Promote it through the existing model registry only if promotion gates pass.
