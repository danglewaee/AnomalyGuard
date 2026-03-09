from collections import deque
from dataclasses import dataclass
from typing import Deque

import numpy as np
from sklearn.ensemble import IsolationForest

from app.schemas import WaterReading

try:
    import shap  # type: ignore
except Exception:
    shap = None


FEATURES = ["ph", "tds", "turbidity", "temperature_c", "do_mg_l", "flow_l_min"]

RULES = {
    "ph": (6.5, 8.5),
    "tds": (0.0, 500.0),
    "turbidity": (0.0, 5.0),
    "temperature_c": (0.0, 35.0),
    "do_mg_l": (5.0, 14.0),
    "flow_l_min": (0.5, 20.0),
}


@dataclass
class DetectionResult:
    is_anomaly: bool
    score: float
    severity: str
    reasons: list[str]
    contributions: dict[str, float]


class HybridAnomalyDetector:
    def __init__(self, window_size: int = 300) -> None:
        self.window_size = window_size
        self.history: Deque[np.ndarray] = deque(maxlen=window_size)
        self.model = IsolationForest(contamination=0.05, random_state=42)
        self.model_ready = False
        self.last_vector: np.ndarray | None = None

    def _to_vector(self, reading: WaterReading) -> np.ndarray:
        return np.array([getattr(reading, name) for name in FEATURES], dtype=float)

    def _fit_if_needed(self) -> None:
        if len(self.history) < 80:
            return
        data = np.vstack(self.history)
        self.model.fit(data)
        self.model_ready = True

    def explain(self, reading: WaterReading) -> dict[str, float]:
        x = self._to_vector(reading)
        if self.model_ready and shap is not None:
            try:
                explainer = shap.TreeExplainer(self.model)
                values = explainer.shap_values(x.reshape(1, -1))
                row = values[0] if isinstance(values, list) else values[0]
                return {FEATURES[i]: float(abs(row[i])) for i in range(len(FEATURES))}
            except Exception:
                pass

        if len(self.history) > 10:
            data = np.vstack(self.history)
            mean = data.mean(axis=0)
            std = np.where(data.std(axis=0) < 1e-6, 1.0, data.std(axis=0))
            z = np.abs((x - mean) / std)
            return {FEATURES[i]: float(z[i]) for i in range(len(FEATURES))}

        return {f: 0.0 for f in FEATURES}

    def score(self, reading: WaterReading) -> DetectionResult:
        x = self._to_vector(reading)
        self.last_vector = x
        self.history.append(x)
        self._fit_if_needed()

        reasons: list[str] = []
        contributions: dict[str, float] = {}

        if len(self.history) > 10:
            data = np.vstack(self.history)
            mean = data.mean(axis=0)
            std = data.std(axis=0)
            std = np.where(std < 1e-6, 1.0, std)
            z = np.abs((x - mean) / std)
        else:
            z = np.zeros_like(x)

        z_score = float(np.max(z) / 6.0)

        rule_penalty = 0.0
        for i, feature in enumerate(FEATURES):
            lo, hi = RULES[feature]
            value = float(x[i])
            if value < lo or value > hi:
                delta = abs(value - lo) if value < lo else abs(value - hi)
                penalty = min(0.5, delta / (hi - lo + 1e-6))
                rule_penalty += penalty
                reasons.append(f"{feature} outside safe range")

        if self.model_ready:
            if_score = -float(self.model.score_samples([x])[0])
            if_score = max(0.0, min(if_score, 1.0))
        else:
            if_score = 0.0

        combined = 0.5 * z_score + 0.3 * if_score + 0.2 * min(rule_penalty, 1.0)
        is_anomaly = combined >= 0.45 or rule_penalty >= 0.4

        raw_contrib = self.explain(reading)
        top = sorted(raw_contrib.items(), key=lambda kv: kv[1], reverse=True)[:3]
        contributions = {k: float(v) for k, v in top}

        if not reasons and is_anomaly:
            reasons.append("statistical deviation from recent baseline")

        severity = "low"
        if combined >= 0.7:
            severity = "high"
        elif combined >= 0.55:
            severity = "medium"

        return DetectionResult(
            is_anomaly=is_anomaly,
            score=round(combined, 3),
            severity=severity,
            reasons=reasons,
            contributions=contributions,
        )
