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
- `deployment/community-impact/default.json`: default community messaging profile for downstream impact
- `deployment/community-impact/*.json`: deployment-ready examples for urban river, aquaculture-heavy, and rural drinking-water contexts
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

Frontend routes:

- `http://localhost:5173/ops`
- `http://localhost:5173/community`

Current UI split:

- `Ops View`: ingest, raw alerts, incident workflow, and device control
- `Community View`: public-safe status cards, a lightweight geographic zone map built from station coordinates, and downstream impact priorities for public-facing audiences and water-dependent sites

## Local Backend (without Docker)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Run backend tests:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Authentication

Request admin token:

```powershell
curl -X POST "http://localhost:8000/api/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Use returned bearer token for protected endpoints (`/api/ingest/*`, `/api/stream/start`, `/api/stream/stop`).

Incident workflow endpoints:

- `POST /api/incidents/{alert_id}/acknowledge`
- `POST /api/incidents/{alert_id}/resolve`
- `POST /api/incidents/{alert_id}/reopen`
- `POST /api/alerts/{alert_id}/review`
  - body: `{"label":"true_anomaly"}` or `{"label":"false_positive"}`
- `GET /api/alerts/labeled/export?format=csv`
  - admin-only export for reviewed alerts, optionally filtered by `label`, `station_id`, `since_minutes`, and `limit`
- `GET /api/alerts/labeled/manifest`
  - admin-only retraining manifest with dataset fingerprint, label balance, station coverage, suggested split, and export URLs

Job status endpoint:

- `GET /api/jobs/{job_id}`
  - returns `queued`, `running`, `succeeded`, or `failed` for background ingest jobs

## Ingest Real Data

Vietnam feed (Open-Meteo at VN coordinates):

```powershell
curl -X POST "http://localhost:8000/api/ingest/vn?station_id=mekong-can-tho&days=30" \
  -H "Authorization: Bearer <TOKEN>"
```

The ingest endpoint now returns a job record immediately. Poll `GET /api/jobs/{job_id}` until it reaches `succeeded` or `failed`.
Successful ingest job payloads now report both `inserted_readings` and `skipped_duplicates`, so repeated pulls of the same window are idempotent for API-feed ingestion.

USGS feed:

```powershell
curl -X POST "http://localhost:8000/api/ingest/usgs?site_no=01646500&hours=24" \
  -H "Authorization: Bearer <TOKEN>"
```

## Device Telemetry

ESP32-compatible telemetry ingest:

```powershell
curl -X POST "http://localhost:8000/api/device/telemetry" \
  -H "Content-Type: application/json" \
  -H "X-Device-Key: anomalyguard-device-key" \
  -d "{\"station_id\":\"esp32-device-001\",\"station_name\":\"Home Device\",\"ph\":7.2,\"tds\":420,\"waterTemp\":28.4,\"temp\":31.1,\"hum\":68.5,\"weight\":350.0,\"isFeeding\":false}"
```

Admin control update for device:

```powershell
curl -X PUT "http://localhost:8000/api/device/control/esp32-device-001" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"direction\":0,\"pump\":true,\"isFeeding\":false,\"weight\":120,\"hour\":8,\"minute\":30}"
```

Device polling endpoint for latest control payload:

```powershell
curl "http://localhost:8000/api/device/control/esp32-device-001" \
  -H "X-Device-Key: anomalyguard-device-key"
```

Bring-up helpers:

- checklist: `docs/device-bringup.md`
- sample payload: `docs/device-sample-telemetry.json`
- local smoke test: `scripts/device-smoke-test.ps1`

Optional frontend env:

- `VITE_API_BASE`
- `VITE_WS_URL`

Optional backend env:

- `COMMUNITY_IMPACT_PROFILE_PATH`
  - points to a JSON profile that defines downstream audience groups, priority sites, and corridor wording for community updates
  - default profile lives at `deployment/community-impact/default.json`

Demo helpers:

- `GET /api/community/impact-profiles`
  - lists built-in impact profiles available for the community view selector
- `GET /api/community/overview?since_minutes=720&impact_profile=urban-river`
  - renders the community summary using a selected built-in profile without changing env configuration

## Community View Direction

Planning docs for the next product phase:

- roadmap: `docs/community-view-roadmap.md`
- implementation notes: `docs/community-view-implementation-notes.md`

## Platform Upgrade Direction

FAANG-grade platform planning docs:

- index: `docs/platform-upgrade/README.md`
- target architecture: `docs/platform-upgrade/target-architecture.md`
- migration roadmap: `docs/platform-upgrade/migration-roadmap.md`
- phase 1 backlog: `docs/platform-upgrade/phase-1-foundation-backlog.md`
- CI/CD and ops playbook: `docs/platform-upgrade/ci-cd-and-ops-playbook.md`

## Observability

- Prometheus metrics endpoint: `GET /metrics`
- Alert/readings counters and ingest request latency are exported
- Job lifecycle metrics now include status transitions, queue time, and run time by job type
- Ingest observability now tracks completed batches and duplicate readings skipped per source

## Notes

- VN ingest uses real hydro/weather feed; quality variables include derived proxies for compatibility with the anomaly pipeline.
- Kafka publishing is controlled via `ENABLE_KAFKA_PUBLISH` in env.
