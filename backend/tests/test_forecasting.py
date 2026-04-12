from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOW_INSECURE_DEFAULTS", "false")
os.environ.setdefault("JWT_SECRET_KEY", "anomalyguard-test-jwt-0123456789abcdef0123456789")
os.environ.setdefault("ADMIN_USERNAME", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "AnomalyGuardTestAdmin!2026")
os.environ.setdefault("DEVICE_API_KEY", "anomalyguard-test-device-key-0123456789")
os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://testserver")


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEPS_ROOT = BACKEND_ROOT / ".deps"
if DEPS_ROOT.exists() and str(DEPS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEPS_ROOT))

from app.schemas import WaterReading
from app.services.deep_forecasting import LSTMForecastResult
from app.services.forecasting import build_water_quality_forecast


UTC = timezone.utc


def _reading(index: int, *, turbidity: float = 2.0, ph: float = 7.2) -> WaterReading:
    return WaterReading(
        timestamp=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(hours=index),
        station_id="mekong-can-tho",
        ph=ph,
        tds=220.0 + index * 0.1,
        turbidity=turbidity,
        temperature_c=28.0,
        do_mg_l=7.0,
        flow_l_min=10.0,
    )


class ForecastingTests(unittest.TestCase):
    def test_forecast_returns_empty_with_clear_limitation_when_data_is_insufficient(self) -> None:
        response = build_water_quality_forecast(
            [_reading(0)],
            station_id="mekong-can-tho",
            horizon_hours=[6],
            method="auto",
        )

        self.assertEqual(response.data_points, 1)
        self.assertEqual(response.forecasts, [])
        self.assertTrue(any("At least two readings" in item for item in response.limitations))

    def test_lag_linear_forecast_flags_future_boundary_risk(self) -> None:
        readings = [_reading(index, turbidity=1.0 + index * 0.18) for index in range(48)]

        response = build_water_quality_forecast(
            readings,
            station_id="mekong-can-tho",
            horizon_hours=[6],
            method="lag_linear",
            lag_steps=6,
        )

        self.assertEqual(response.forecasts[0].method, "lag_linear")
        self.assertIn(response.forecasts[0].risk_level, {"warning", "critical"})
        turbidity = next(signal for signal in response.forecasts[0].signals if signal.signal == "turbidity")
        self.assertGreater(turbidity.predicted_value, turbidity.safe_max)
        self.assertGreaterEqual(turbidity.risk_score, 0.5)

    def test_auto_forecast_falls_back_to_moving_average_when_lag_windows_are_insufficient(self) -> None:
        readings = [_reading(index, turbidity=2.0 + index * 0.1) for index in range(5)]

        response = build_water_quality_forecast(
            readings,
            station_id="mekong-can-tho",
            horizon_hours=[12],
            method="auto",
            lag_steps=6,
        )

        self.assertEqual(response.forecasts[0].method, "moving_average")
        self.assertTrue(response.forecasts[0].warnings)

    def test_lstm_request_falls_back_cleanly_when_torch_is_unavailable(self) -> None:
        readings = [_reading(index, turbidity=2.0 + index * 0.05) for index in range(20)]

        with patch(
            "app.services.forecasting.forecast_with_lstm",
            return_value=LSTMForecastResult(prediction=None, warning="PyTorch is not installed."),
        ):
            response = build_water_quality_forecast(
                readings,
                station_id="mekong-can-tho",
                horizon_hours=[6],
                method="lstm",
                lag_steps=6,
            )

        self.assertEqual(response.requested_method, "lstm")
        self.assertIn(response.forecasts[0].method, {"lag_linear", "moving_average", "persistence", "lstm"})
        self.assertTrue(any("lstm" in warning.lower() or "pytorch" in warning.lower() for warning in response.forecasts[0].warnings))
        self.assertIn("lstm", response.methods_considered)
