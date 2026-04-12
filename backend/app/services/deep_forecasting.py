from dataclasses import dataclass

import numpy as np


try:
    import torch
    from torch import nn
except Exception:  # pragma: no cover - optional deep-learning runtime
    torch = None
    nn = None


@dataclass
class LSTMForecastResult:
    prediction: np.ndarray | None
    warning: str | None = None
    epochs_trained: int = 0


if nn is not None:

    class _WaterQualityLSTM(nn.Module):
        def __init__(self, feature_count: int, hidden_size: int) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size=feature_count, hidden_size=hidden_size, batch_first=True)
            self.head = nn.Linear(hidden_size, feature_count)

        def forward(self, x):  # noqa: ANN001 - torch tensor type is optional at import time
            output, _ = self.lstm(x)
            return self.head(output[:, -1, :])

else:
    _WaterQualityLSTM = None


def forecast_with_lstm(
    values: np.ndarray,
    *,
    horizon_steps: int,
    sequence_length: int = 12,
    epochs: int = 80,
    hidden_size: int = 24,
) -> LSTMForecastResult:
    if torch is None or _WaterQualityLSTM is None:
        return LSTMForecastResult(
            prediction=None,
            warning="PyTorch is not installed; install backend/requirements-dl.txt to enable LSTM forecasts.",
        )

    required_points = sequence_length + horizon_steps + 8
    if len(values) < required_points:
        return LSTMForecastResult(
            prediction=None,
            warning=f"lstm needs at least {required_points} readings for this horizon",
        )

    x_rows: list[np.ndarray] = []
    y_rows: list[np.ndarray] = []
    for start in range(0, len(values) - sequence_length - horizon_steps + 1):
        x_rows.append(values[start : start + sequence_length])
        y_rows.append(values[start + sequence_length + horizon_steps - 1])

    if len(x_rows) < 8:
        return LSTMForecastResult(prediction=None, warning="lstm did not have enough training windows")

    train_x = np.stack(x_rows).astype("float32")
    train_y = np.stack(y_rows).astype("float32")
    mean = train_x.reshape(-1, values.shape[1]).mean(axis=0)
    std = train_x.reshape(-1, values.shape[1]).std(axis=0)
    std = np.where(std < 1e-6, 1.0, std).astype("float32")

    train_x = (train_x - mean) / std
    train_y = (train_y - mean) / std
    current_window = ((values[-sequence_length:].astype("float32") - mean) / std)[None, :, :]

    torch.manual_seed(42)
    model = _WaterQualityLSTM(feature_count=values.shape[1], hidden_size=hidden_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = nn.SmoothL1Loss()

    x_tensor = torch.from_numpy(train_x)
    y_tensor = torch.from_numpy(train_y)
    model.train()
    for _ in range(max(1, epochs)):
        optimizer.zero_grad()
        prediction = model(x_tensor)
        loss = loss_fn(prediction, y_tensor)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

    model.eval()
    with torch.no_grad():
        forecast = model(torch.from_numpy(current_window)).numpy()[0]

    prediction = forecast * std + mean
    return LSTMForecastResult(prediction=prediction.astype(float), epochs_trained=max(1, epochs))
