from datetime import datetime, timedelta, timezone
from typing import Literal

import numpy as np

from app.schemas import ForecastSignalPrediction, WaterQualityForecastPoint, WaterQualityForecastResponse, WaterReading
from app.services.detector import FEATURES, RULES


ForecastMethod = Literal["auto", "persistence", "moving_average", "lag_linear"]
ConcreteForecastMethod = Literal["persistence", "moving_average", "lag_linear"]


_DEFAULT_LIMITATIONS = [
    "This is an early-warning prototype, not a public health determination.",
    "Predictions depend on sensor calibration, station coverage, and missing-data quality.",
    "Deep learning should only be promoted after beating simple baselines on held-out data.",
]

_DEEP_LEARNING_NEXT_STEPS = [
    "Collect longer station-level time series with verified sensor calibration metadata.",
    "Benchmark persistence, moving-average, and lag-linear baselines before LSTM/Informer models.",
    "Train sequence models only after there are enough contiguous readings per station and season.",
    "Evaluate both value error (MAE/RMSE) and warning utility (precision, recall, false alarm rate, lead time).",
]


def _reading_vector(reading: WaterReading) -> np.ndarray:
    return np.array([float(getattr(reading, feature)) for feature in FEATURES], dtype=float)


def _infer_cadence_minutes(readings: list[WaterReading]) -> float | None:
    if len(readings) < 2:
        return None

    deltas: list[float] = []
    ordered = sorted(readings, key=lambda item: item.timestamp)
    for previous, current in zip(ordered, ordered[1:]):
        seconds = (current.timestamp - previous.timestamp).total_seconds()
        if seconds > 0:
            deltas.append(seconds / 60.0)

    if not deltas:
        return None
    return float(np.median(np.array(deltas, dtype=float)))


def _risk_level(score: float) -> Literal["stable", "watch", "warning", "critical"]:
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "warning"
    if score >= 0.25:
        return "watch"
    return "stable"


def _signal_risk(feature: str, current_value: float, predicted_value: float) -> ForecastSignalPrediction:
    safe_min, safe_max = RULES[feature]
    span = max(safe_max - safe_min, 1e-6)
    risk_score = 0.0
    reason = "forecast remains inside the detector safe band"

    if predicted_value < safe_min:
        distance = (safe_min - predicted_value) / span
        risk_score = min(1.0, 0.55 + distance)
        reason = "forecast drops below detector safe band"
    elif predicted_value > safe_max:
        distance = (predicted_value - safe_max) / span
        risk_score = min(1.0, 0.55 + distance)
        reason = "forecast exceeds detector safe band"
    else:
        edge_distance = min(predicted_value - safe_min, safe_max - predicted_value) / span
        trend_delta = abs(predicted_value - current_value) / span
        if edge_distance < 0.1 and trend_delta > 0.05:
            risk_score = 0.35
            reason = "forecast remains legal but moves close to a detector boundary"
        elif trend_delta > 0.2:
            risk_score = 0.25
            reason = "forecast changes quickly while staying inside the safe band"

    return ForecastSignalPrediction(
        signal=feature,
        current_value=round(current_value, 4),
        predicted_value=round(float(predicted_value), 4),
        delta=round(float(predicted_value - current_value), 4),
        safe_min=float(safe_min),
        safe_max=float(safe_max),
        risk_level=_risk_level(risk_score),
        risk_score=round(float(risk_score), 3),
        reason=reason,
    )


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    size = min(max(window, 1), len(values))
    return values[-size:].mean(axis=0)


def _lag_linear_forecast(values: np.ndarray, horizon_steps: int, lag_steps: int) -> tuple[np.ndarray | None, str | None]:
    if len(values) < lag_steps + horizon_steps + 4:
        return None, f"lag_linear needs at least {lag_steps + horizon_steps + 4} readings for this horizon"

    x_rows: list[np.ndarray] = []
    y_rows: list[np.ndarray] = []
    for start in range(0, len(values) - lag_steps - horizon_steps + 1):
        x_rows.append(values[start : start + lag_steps].reshape(-1))
        y_rows.append(values[start + lag_steps + horizon_steps - 1])

    if len(x_rows) < 4:
        return None, "lag_linear did not have enough training windows"

    x = np.vstack(x_rows)
    y = np.vstack(y_rows)
    x_mean = x.mean(axis=0)
    x_std = np.where(x.std(axis=0) < 1e-6, 1.0, x.std(axis=0))
    x_scaled = (x - x_mean) / x_std
    x_design = np.column_stack([np.ones(len(x_scaled)), x_scaled])

    try:
        coefficients = np.linalg.pinv(x_design) @ y
    except np.linalg.LinAlgError:
        return None, "lag_linear matrix solve failed; falling back to baseline"

    current_window = values[-lag_steps:].reshape(1, -1)
    current_scaled = (current_window - x_mean) / x_std
    current_design = np.column_stack([np.ones(1), current_scaled])
    return (current_design @ coefficients)[0], None


def _confidence(method: ConcreteForecastMethod, data_points: int, required_points: int, horizon_steps: int) -> float:
    if data_points <= 0:
        return 0.0
    coverage = min(1.0, data_points / max(required_points, 1))
    horizon_penalty = max(0.35, 1.0 - min(horizon_steps, 48) * 0.01)
    method_weight = {"persistence": 0.45, "moving_average": 0.6, "lag_linear": 0.75}[method]
    return round(float(max(0.1, min(0.95, coverage * horizon_penalty * method_weight + 0.15))), 3)


def build_water_quality_forecast(
    readings: list[WaterReading],
    *,
    station_id: str | None,
    horizon_hours: list[int],
    method: ForecastMethod = "auto",
    moving_window: int = 12,
    lag_steps: int = 6,
) -> WaterQualityForecastResponse:
    ordered = sorted(readings, key=lambda item: item.timestamp)
    generated_at = datetime.now(timezone.utc)
    cadence_minutes = _infer_cadence_minutes(ordered)
    limitations = list(_DEFAULT_LIMITATIONS)

    if len(ordered) < 2:
        return WaterQualityForecastResponse(
            generated_at=generated_at,
            station_id=station_id,
            requested_method=method,
            data_points=len(ordered),
            cadence_minutes=cadence_minutes,
            features=list(FEATURES),
            methods_considered=["persistence"],
            forecasts=[],
            limitations=limitations + ["At least two readings are required to produce a forecast."],
            deep_learning_next_steps=list(_DEEP_LEARNING_NEXT_STEPS),
        )

    if cadence_minutes is None or cadence_minutes <= 0:
        cadence_minutes = 60.0
        limitations.append("Cadence could not be inferred, so forecast horizons assume hourly readings.")

    values = np.vstack([_reading_vector(reading) for reading in ordered])
    current = values[-1]
    last_timestamp = ordered[-1].timestamp
    forecasts: list[WaterQualityForecastPoint] = []
    methods_considered = ["persistence", "moving_average", "lag_linear"]

    for horizon in sorted(set(horizon_hours)):
        horizon_steps = max(1, int(round((horizon * 60.0) / cadence_minutes)))
        warnings: list[str] = []
        selected_method: ConcreteForecastMethod
        prediction: np.ndarray | None = None

        if method == "persistence":
            selected_method = "persistence"
            prediction = current
        elif method == "moving_average":
            selected_method = "moving_average"
            prediction = _moving_average(values, moving_window)
        else:
            lag_prediction, lag_warning = _lag_linear_forecast(values, horizon_steps, lag_steps)
            if method == "lag_linear" and lag_prediction is None:
                selected_method = "moving_average" if len(values) >= 3 else "persistence"
                prediction = _moving_average(values, moving_window) if selected_method == "moving_average" else current
                warnings.append(lag_warning or "lag_linear unavailable; used fallback baseline")
            elif lag_prediction is None:
                selected_method = "moving_average" if len(values) >= 3 else "persistence"
                prediction = _moving_average(values, moving_window) if selected_method == "moving_average" else current
                warnings.append(lag_warning or "lag_linear unavailable; used fallback baseline")
            else:
                selected_method = "lag_linear"
                prediction = lag_prediction

        signal_predictions = [
            _signal_risk(feature, float(current[index]), float(prediction[index]))
            for index, feature in enumerate(FEATURES)
        ]
        risk_score = max(signal.risk_score for signal in signal_predictions)
        required_points = lag_steps + horizon_steps + 4 if selected_method == "lag_linear" else moving_window
        forecasts.append(
            WaterQualityForecastPoint(
                horizon_hours=horizon,
                forecast_at=last_timestamp + timedelta(hours=horizon),
                method=selected_method,
                risk_level=_risk_level(risk_score),
                risk_score=round(float(risk_score), 3),
                confidence=_confidence(selected_method, len(values), required_points, horizon_steps),
                signals=signal_predictions,
                warnings=warnings,
            )
        )

    if len(ordered) < 30:
        limitations.append("Fewer than 30 readings are available, so the prototype should be treated as a smoke-test forecast.")

    return WaterQualityForecastResponse(
        generated_at=generated_at,
        station_id=station_id,
        requested_method=method,
        data_points=len(ordered),
        cadence_minutes=round(float(cadence_minutes), 3),
        features=list(FEATURES),
        methods_considered=methods_considered,
        forecasts=forecasts,
        limitations=limitations,
        deep_learning_next_steps=list(_DEEP_LEARNING_NEXT_STEPS),
    )
