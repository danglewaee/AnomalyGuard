import random
from datetime import datetime, timezone

from app.schemas import WaterReading

BASELINES = {
    "mekong-can-tho": {
        "ph": (7.1, 0.2),
        "tds": (230, 25),
        "turbidity": (3.0, 0.8),
        "temperature_c": (28.0, 1.4),
        "do_mg_l": (7.8, 0.7),
        "flow_l_min": (8.0, 1.2),
    },
    "saigon-thu-duc": {
        "ph": (7.3, 0.15),
        "tds": (320, 30),
        "turbidity": (2.4, 0.7),
        "temperature_c": (29.5, 1.0),
        "do_mg_l": (7.1, 0.6),
        "flow_l_min": (6.8, 1.0),
    },
    "red-river-ha-noi": {
        "ph": (7.0, 0.2),
        "tds": (270, 25),
        "turbidity": (2.8, 0.8),
        "temperature_c": (25.0, 2.0),
        "do_mg_l": (8.2, 0.7),
        "flow_l_min": (7.2, 1.1),
    },
}


class WaterReadingSimulator:
    def __init__(self) -> None:
        self.tick_by_station: dict[str, int] = {}

    def next(self, station_id: str) -> WaterReading:
        tick = self.tick_by_station.get(station_id, 0) + 1
        self.tick_by_station[station_id] = tick

        base = BASELINES.get(station_id, BASELINES["mekong-can-tho"])

        ph = random.gauss(*base["ph"])
        tds = random.gauss(*base["tds"])
        turbidity = max(0.0, random.gauss(*base["turbidity"]))
        temperature_c = random.gauss(*base["temperature_c"])
        do_mg_l = random.gauss(*base["do_mg_l"])
        flow_l_min = max(0.0, random.gauss(*base["flow_l_min"]))

        # Pollution-like event bursts.
        if tick % 60 in (0, 1, 2, 3, 4):
            turbidity += random.uniform(6.0, 18.0)
            tds += random.uniform(180, 420)
            do_mg_l -= random.uniform(1.8, 4.2)
            ph += random.choice([-1.4, 1.3])

        # Sensor fault pattern.
        if tick % 95 in (0, 1):
            flow_l_min *= 0.1
            do_mg_l += random.uniform(1.0, 2.0)

        return WaterReading(
            timestamp=datetime.now(timezone.utc),
            station_id=station_id,
            ph=round(ph, 3),
            tds=round(tds, 2),
            turbidity=round(turbidity, 3),
            temperature_c=round(temperature_c, 2),
            do_mg_l=round(do_mg_l, 2),
            flow_l_min=round(flow_l_min, 2),
        )
