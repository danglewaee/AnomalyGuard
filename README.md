# AnomalyGuard Water Pollution MVP

Water-first MVP for real-time anomaly detection in water telemetry.

## MVP Status

- Simulated stream (VN stations) for live demo continuity
- Real VN ingestion path (Open-Meteo flood/weather API at VN coordinates)
- Real-time stream via WebSocket
- Hybrid anomaly detection (rules + z-score + Isolation Forest)
- SQLite persistence for readings/alerts
- Dashboard filters for station/time window and VN ingest action

## Data Region and Time

- VN stations:
  - `mekong-can-tho` (Can Tho, Mekong Delta)
  - `saigon-thu-duc` (Thu Duc, Ho Chi Minh City)
  - `red-river-ha-noi` (Long Bien, Ha Noi)
- `POST /api/ingest/vn` pulls last `N` days of real hydro data for selected VN station coordinates.
- All stored timestamps are UTC.

## Important Data Note

For VN real ingest:

- Real fields: river discharge (flood API), air temperature (weather API)
- Derived proxy fields: pH, TDS, turbidity, DO (estimated from the real hydro/temperature series for anomaly pipeline compatibility)

## Quick Start

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Ingest VN Real Data

```powershell
curl -X POST "http://localhost:8000/api/ingest/vn?station_id=mekong-can-tho&days=30"
```

Or use the dashboard button `Ingest VN Real Data`.

## API Endpoints

- `GET /health`
- `GET /api/meta`
- `GET /api/stations`
- `GET /api/readings/latest?limit=400&station_id=mekong-can-tho&since_minutes=10080`
- `GET /api/alerts/latest?limit=100&station_id=mekong-can-tho&since_minutes=10080`
- `POST /api/ingest/vn?station_id=mekong-can-tho&days=30`
- `POST /api/stream/start`
- `POST /api/stream/stop`
- `WS /ws/stream`
