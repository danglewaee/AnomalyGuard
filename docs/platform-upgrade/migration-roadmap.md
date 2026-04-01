# Platform Upgrade Migration Roadmap

This roadmap translates the target architecture into a sequence that can be implemented without breaking the current product.

The upgrade strategy is:

1. stabilize the repo
2. create service seams
3. harden pipelines
4. add geospatial and ML lifecycle depth
5. scale only after the operating model is credible

## Success Criteria

The platform upgrade is successful when:

- deployments are reproducible
- ingest paths are asynchronous and idempotent
- tests and contracts catch regressions before release
- incidents, community summaries, and model outputs are traceable
- new deployments can swap messaging or region profiles without code edits
- the system can add new models and data sources without rewiring the whole stack

## Phase 0: Baseline Hardening

Target duration:

- 2 to 3 weeks

Goals:

- remove obvious operational fragility
- make the repo safe to extend

Deliverables:

- real backend test suite
- integration tests for auth, incidents, community overview, and device flows
- fix local infrastructure inconsistencies
- define event and API contracts
- structured configuration review

Metrics:

- backend test coverage on critical paths above 60%
- frontend build and smoke checks green in CI
- zero known blocking misconfigurations in Docker Compose

Exit criteria:

- contributors can trust CI
- the local platform starts consistently

## Phase 1: Platform Foundation

Target duration:

- 4 to 6 weeks

Goals:

- create platform seams without forcing a big rewrite

Deliverables:

- route refactor into domain routers
- job-based ingestion API instead of `task.get(...)`
- persistent job records and status polling endpoints
- idempotency keys for ingest operations
- Kafka topic contracts and a real local broker path
- structured logging and OpenTelemetry instrumentation
- CI stages for lint, test, build, and contract checks

Metrics:

- no blocking ingest requests
- p95 ingestion request latency below 500 ms for job creation
- job success rate above 99% in staging
- trace coverage for critical request paths

Exit criteria:

- ingest is asynchronous
- platform seams are clear
- logs, metrics, and traces are available for the main request and worker flows

## Phase 2: Geospatial and Community Intelligence

Target duration:

- 4 to 6 weeks

Goals:

- make community impact and map behavior first-class

Deliverables:

- PostGIS enablement
- `community_zones`, `community_assets`, and zone linkage tables
- `GET /api/community/zones`
- real map layer using `MapLibre`
- asset-aware impact summaries and proximity logic
- subscription-ready community feed endpoints

Metrics:

- zone lookup coverage for monitored stations
- map render latency within UI target budgets
- operator review to community update flow under agreed SLA

Exit criteria:

- the product can answer who may be affected, not just which station changed

## Phase 3: ML Lifecycle and Feedback

Target duration:

- 4 to 6 weeks

Goals:

- move from one-off scoring to managed model operations

Deliverables:

- MLflow registry used as the promotion path
- model metadata tied to code and dataset versions
- operator feedback labels persisted and queryable
- evaluation jobs on recent labeled data
- drift checks on important features and alert volumes
- retraining playbook with manual approval gates

Metrics:

- every deployed model version traceable to code and data
- labeled precision and false-positive metrics visible in dashboards
- drift alerts generated with low noise

Exit criteria:

- model promotion and rollback are explicit
- the system can explain which model produced which anomaly

## Phase 4: Predictive Risk and Feature Platform

Target duration:

- 4 to 8 weeks

Goals:

- add early warning, not just anomaly detection

Deliverables:

- forecasting pipeline
- station and zone level risk forecasts
- feature definitions shared between training and serving
- champion/challenger evaluation for anomaly and forecast models
- operator and community forecast views

Metrics:

- forecast error by horizon
- alert lead time before severe incidents
- reduction in high-noise false alerts

Exit criteria:

- operators can act on near-term risk forecasts, not just past anomalies

## Phase 5: Tenant, Notifications, and Resilience

Target duration:

- 6+ weeks

Goals:

- prepare for serious multi-region or multi-client operation

Deliverables:

- tenant-aware data boundaries
- notification dispatcher and delivery audit trail
- role-based subscriptions
- managed cloud infrastructure modules
- backup and disaster recovery runbooks
- environment promotion playbook from dev to staging to prod

Metrics:

- delivery success for notifications
- recovery time objective for platform incidents
- environment creation time via Terraform

Exit criteria:

- the platform can support multiple deployments without code forks

## Recommended Team Shape

Lean team:

- 1 backend/platform engineer
- 1 ML engineer
- 1 frontend/product engineer
- 1 DevOps/SRE-capable engineer

Larger team:

- 2 backend/platform engineers
- 1 data engineer
- 1 ML engineer
- 1 frontend engineer
- 1 DevOps/SRE

## Risks and Controls

Risk:

- platform work outruns product value

Control:

- keep operator and community value measurable each phase

Risk:

- too many new tools at once

Control:

- add tools only when the previous layer has clear ownership and tests

Risk:

- microservice fragmentation too early

Control:

- start with modular monolith boundaries and split deployables later

## What To Avoid During Migration

- rewriting every service at once
- adding a feature store before feature definitions are stable
- moving to Kubernetes before CI and observability are credible
- introducing multiple new databases without ownership boundaries
- deploying multiple models without evaluation and rollback rules
