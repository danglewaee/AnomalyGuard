# Architecture v2 (Polyglot, Level C)

## Design Principles

- Keep ML and optimization in Python for iteration speed.
- Move Kubernetes control/apply path to Go for production-grade reliability.
- Use Rust for high-throughput telemetry ingress where latency and memory matter.
- Split operational time-series storage and analytical storage for scale.

## Service Map

### Control Plane (Go)

- `autopilot-agent`:
  - Runs in cluster.
  - Pulls policy and recommendations.
  - Applies guarded rollout actions.
- `autopilot-controller`:
  - Watches CRDs (`AutopilotPolicy`, `AutopilotPlan`).
  - Coordinates safe apply via Argo Rollouts.

### Intelligence Plane (Python)

- `predictor` (`PyTorch`):
  - Multi-horizon forecasting (5m/15m/60m).
- `optimizer` (`OR-Tools`, optional RL):
  - MILP for instance mix / cost / constraints.
- `simulator`:
  - Latency and risk simulation.
- `policy-evaluator`:
  - Calls OPA/Rego guardrails before apply.

### Ingestion Plane (Rust)

- `telemetry-gateway`:
  - High-throughput metric ingest.
  - Schema validation and lightweight aggregation.
  - Produces events to Kafka.

### Stream + Storage

- `Kafka`: event backbone.
- `Flink`: streaming windows, feature joins, online anomaly signals.
- `TimescaleDB`: short-horizon operational state and model inputs.
- `ClickHouse`: cost analytics, benchmark reports, long-range queries.

### API + UX

- `decision-api` (REST): external-facing endpoints and artifacts.
- `dashboard`: what-if, plan diff, cost/risk visibility.

## Protocols

- North-south: REST/JSON.
- East-west: gRPC + Protobuf.

## Governance and Safety

- OPA/Rego policy checks:
  - SLO floor.
  - Max downscale step.
  - Spot exposure cap.
- Argo Rollouts for canary + rollback.

## Observability

- OpenTelemetry instrumentation in all services.
- Prometheus metrics + Grafana dashboards.
- Tempo traces for end-to-end decision latency.

## Repo Layout Target

- `cmd/agent` (Go)
- `cmd/controller` (Go)
- `services/predictor` (Python)
- `services/optimizer` (Python)
- `services/simulator` (Python)
- `services/policy` (Python + OPA integration)
- `services/telemetry-gateway` (Rust)
- `stream/flink-jobs`
- `pkg/proto`
- `charts/autopilot`
