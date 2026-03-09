# AI-AnomalyGuard

AI-powered anomaly detection platform for water monitoring, upgraded to a production-style multi-tech stack.

## Upgraded Stack

- API: FastAPI + WebSockets
- Storage: PostgreSQL (TimescaleDB extension attempt) via SQLAlchemy
- Async jobs: Celery + Redis
- Streaming integration: Kafka publisher for alerts
- ML: Isolation Forest + SHAP-ready explainability
- ML ops: MLflow metric logging
- Monitoring: Prometheus + Grafana
- Auth: JWT (OAuth2 password flow) + admin RBAC
- Infra: Docker Compose + Terraform scaffold
- CI: GitHub Actions (backend compile + frontend build)

## Project Structure

- `backend/app/main.py`: API, RBAC, ingest orchestration, metrics endpoint
- `backend/app/services/store_pg.py`: PostgreSQL data layer
- `backend/app/services/detector.py`: hybrid anomaly scoring with SHAP fallback
- `backend/app/tasks.py`: Celery ingestion tasks
- `docker-compose.yml`: full local platform stack
- `observability/prometheus/prometheus.yml`: Prometheus scrape config
- `infra/terraform/main.tf`: Terraform scaffold
- `.github/workflows/ci.yml`: CI pipeline

## Run Full Stack (Docker)

```powershell
docker compose up --build
```

Services:
- API: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (`admin/admin`)

## Local Backend (without Docker)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Authentication

Request admin token:

```powershell
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Use returned bearer token for protected endpoints (`/api/ingest/*`, `/api/stream/start`, `/api/stream/stop`).

## Ingest Real Data

Vietnam feed (Open-Meteo at VN coordinates):

```powershell
curl -X POST "http://localhost:8000/api/ingest/vn?station_id=mekong-can-tho&days=30" \
  -H "Authorization: Bearer <TOKEN>"
```

USGS feed:

```powershell
curl -X POST "http://localhost:8000/api/ingest/usgs?site_no=01646500&hours=24" \
  -H "Authorization: Bearer <TOKEN>"
```

## Observability

- Prometheus metrics endpoint: `GET /metrics`
- Alert/readings counters and ingest latency are exported

## Notes

- VN ingest uses real hydro/weather feed; quality variables include derived proxies for compatibility with the anomaly pipeline.
- Kafka publishing is controlled via `ENABLE_KAFKA_PUBLISH` in env.
