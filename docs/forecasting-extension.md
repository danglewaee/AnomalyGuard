# Forecasting Extension

AnomalyGuard now includes a lightweight forecasting prototype that reframes the original monitoring system from reactive anomaly detection into early-warning risk forecasting.

The extension is intentionally baseline-first. It does not claim that LSTM or Transformer models are automatically better. Instead, it follows the lesson from water-quality forecasting literature: compare simple baselines before promoting deep learning.

## Current Scope

- Input signals: `pH`, `TDS`, `turbidity`, `temperature`, `DO`, and `flow`
- Forecast horizons: default `6h`, `12h`, and `24h`
- Methods:
  - `persistence`: future value equals latest value
  - `moving_average`: future value equals recent window mean
  - `lag_linear`: a lightweight linear lag model over recent multivariate windows
  - `auto`: uses `lag_linear` when enough station history exists, otherwise falls back to a baseline
- Output:
  - predicted signal values
  - signal-level risk levels
  - overall station risk level
  - confidence estimate
  - limitations and deep-learning next steps

## Why Baseline First

For a public-interest water project, using a complex model is not enough. The system has to earn trust. A simple baseline provides a reference point for whether LSTM, Informer, or other sequence models are actually improving:

- Value accuracy: `MAE`, `RMSE`
- Warning utility: precision, recall, false alarm rate, and lead time
- Operational trust: whether alerts are stable enough for operators or local authorities to act on

## API

```powershell
curl "http://localhost:8000/api/forecasts/water-quality?station_id=mekong-can-tho&horizon_hours=6&horizon_hours=12&method=auto"
```

The endpoint is read-only and station-level. If `station_id` is omitted, it uses the default station.

## Interview Framing

Use this wording when explaining the project:

> The original project detected water-quality anomalies from sensor readings. The forecasting extension asks a more useful question: can we estimate risk before the water becomes unsafe? I started with persistence, moving-average, and lag-linear baselines because in public-interest work, credibility matters more than model complexity. LSTM or Transformer-style models would be the next step only after they beat these baselines on held-out station data and improve early-warning lead time without causing too many false alarms.

## Deep Learning Roadmap

- Collect longer calibrated station-level time series.
- Add weather, tide, rainfall, upstream discharge, and seasonal context.
- Train an LSTM/Informer/LTSF-style model as a candidate artifact.
- Compare it against persistence, moving average, and lag-linear baselines.
- Promote it through the existing model registry only if promotion gates pass.

