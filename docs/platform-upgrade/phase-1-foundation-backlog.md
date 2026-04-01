# Phase 1 Foundation Backlog

This backlog is the execution layer for the first platform-upgrade phase.

The goal of Phase 1 is not to finish the whole platform. The goal is to make the repo structurally ready for everything that comes next.

## Phase 1 Outcomes

By the end of Phase 1, the repo should have:

- asynchronous ingest jobs instead of blocking requests
- clear API domain boundaries
- stronger CI and test coverage
- real event contracts for ingest and incident flows
- structured logs, metrics, and traces on critical paths
- a local stack that resembles the intended platform more honestly

## Workstream A: Backend Domain Refactor

Deliverables:

- create `backend/app/api/`
- move route handlers into:
  - `ops.py`
  - `community.py`
  - `device.py`
  - `incidents.py`
  - `jobs.py`
  - `auth.py`
- keep `main.py` as composition root only

Definition of done:

- route registration happens through routers
- business logic is not embedded directly in `main.py`

## Workstream B: Job-Based Ingestion

Deliverables:

- add persistent job model and schema
- replace `task.get(...)` in ingest endpoints with:
  - create job
  - enqueue work
  - return `job_id`
  - poll `GET /api/jobs/{job_id}`
- capture job states:
  - `queued`
  - `running`
  - `succeeded`
  - `failed`

Definition of done:

- ingest request latency no longer depends on external fetch duration
- failed jobs preserve reason and timestamps

## Workstream C: Event Contracts and Kafka Readiness

Deliverables:

- define event envelopes for:
  - telemetry received
  - reading ingested
  - anomaly detected
  - incident updated
- add schema version and idempotency fields
- make local Docker Compose honest about Kafka or disable the path clearly when absent

Definition of done:

- event payloads are explicit and versioned
- local eventing path is understandable and testable

## Workstream D: Testing and CI

Deliverables:

- backend unit tests for:
  - detector output shape
  - community summary builder
  - incident transitions
  - impact profile loading
- API integration tests for:
  - auth token flow
  - incident endpoints
  - community overview
  - job status endpoint
- frontend smoke tests for route rendering and profile selector behavior
- CI stages:
  - lint
  - backend tests
  - frontend build
  - contract checks

Definition of done:

- no core path is protected only by compile checks
- CI failures explain whether code, contracts, or build assets broke

## Workstream E: Observability Foundation

Deliverables:

- structured logs for API, jobs, workers, and notifications
- OpenTelemetry middleware in API and worker entry points
- new metrics:
  - ingest job creation count
  - ingest queue backlog
  - ingest completion latency
  - community summary generation time
  - websocket freshness
- dashboards for critical service and ML indicators

Definition of done:

- platform operators can see failures before users report them

## Workstream F: Infrastructure Baseline

Deliverables:

- clean Docker Compose for local truth
- Docker image build conventions
- staging deployment script or manifest set
- Terraform module plan for:
  - database
  - Redis
  - Kafka
  - app runtime

Definition of done:

- there is a credible path from local to staging

## Workstream G: Product Seams That Unlock Later ML Work

Deliverables:

- operator labeling endpoints and storage
- `true_anomaly`, `false_positive`, `expected_event`, `unresolved`
- incident notes and review timestamps
- community summary remains profile-driven and deployment-safe

Definition of done:

- supervised evaluation can start in later phases without schema redesign

## Suggested PR Sequence

1. add test harness and first backend tests
2. add job models and schemas
3. add `jobs` API and refactor ingest endpoints
4. extract routers from `main.py`
5. add event envelope helpers and contract tests
6. fix Docker Compose eventing truth
7. add OpenTelemetry and structured logging
8. add operator labeling storage and endpoints
9. add frontend smoke tests and CI expansion
10. tighten README and operational docs

## Exit Checklist

- no blocking ingest calls remain in public API handlers
- `main.py` is no longer the main dumping ground
- profile-driven community messaging still works
- tests cover incidents, community summaries, jobs, and profiles
- local stack startup path is documented and believable
- staging rollout steps exist for the new seams
