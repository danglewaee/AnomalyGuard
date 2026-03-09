import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from app.schemas import AnomalyAlert, WaterReading


class SQLiteStore:
    def __init__(self, db_path: str = "data/anomalyguard.db") -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    timestamp TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    ph REAL NOT NULL,
                    tds REAL NOT NULL,
                    turbidity REAL NOT NULL,
                    temperature_c REAL NOT NULL,
                    do_mg_l REAL NOT NULL,
                    flow_l_min REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    score REAL NOT NULL,
                    reasons TEXT NOT NULL,
                    feature_contributions TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_station_time ON readings (station_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_station_time ON alerts (station_id, timestamp)")

    def add_reading(self, reading: WaterReading) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO readings (timestamp, station_id, ph, tds, turbidity, temperature_c, do_mg_l, flow_l_min)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reading.timestamp.isoformat(),
                    reading.station_id,
                    reading.ph,
                    reading.tds,
                    reading.turbidity,
                    reading.temperature_c,
                    reading.do_mg_l,
                    reading.flow_l_min,
                ),
            )

    def add_alert(self, alert: AnomalyAlert) -> None:
        import json

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO alerts (id, timestamp, station_id, severity, score, reasons, feature_contributions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.timestamp.isoformat(),
                    alert.station_id,
                    alert.severity,
                    alert.score,
                    json.dumps(alert.reasons),
                    json.dumps(alert.feature_contributions),
                ),
            )

    def latest_readings(self, limit: int, station_id: str | None = None, since_minutes: int | None = None) -> list[WaterReading]:
        where = []
        args: list[object] = []

        if station_id:
            where.append("station_id = ?")
            args.append(station_id)

        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            where.append("timestamp >= ?")
            args.append(since.isoformat())

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT timestamp, station_id, ph, tds, turbidity, temperature_c, do_mg_l, flow_l_min
                FROM readings
                {where_sql}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (*args, max(1, min(limit, 2000))),
            ).fetchall()

        items = [
            WaterReading(
                timestamp=datetime.fromisoformat(r["timestamp"]),
                station_id=r["station_id"],
                ph=r["ph"],
                tds=r["tds"],
                turbidity=r["turbidity"],
                temperature_c=r["temperature_c"],
                do_mg_l=r["do_mg_l"],
                flow_l_min=r["flow_l_min"],
            )
            for r in rows
        ]
        items.reverse()
        return items

    def latest_alerts(self, limit: int, station_id: str | None = None, since_minutes: int | None = None) -> list[AnomalyAlert]:
        import json

        where = []
        args: list[object] = []

        if station_id:
            where.append("station_id = ?")
            args.append(station_id)

        if since_minutes and since_minutes > 0:
            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            where.append("timestamp >= ?")
            args.append(since.isoformat())

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, timestamp, station_id, severity, score, reasons, feature_contributions
                FROM alerts
                {where_sql}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (*args, max(1, min(limit, 1000))),
            ).fetchall()

        return [
            AnomalyAlert(
                id=r["id"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                station_id=r["station_id"],
                severity=r["severity"],
                score=r["score"],
                reasons=json.loads(r["reasons"]),
                feature_contributions=json.loads(r["feature_contributions"]),
            )
            for r in rows
        ]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            reading_count = conn.execute("SELECT COUNT(*) AS c FROM readings").fetchone()["c"]
            alert_count = conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
        return {"readings": int(reading_count), "alerts": int(alert_count)}
