# Self-Optimizing Cloud Infrastructure AI (MVP -> FAANG Hardening)

MVP system that simulates cloud telemetry, predicts workload, recommends scaling actions, and visualizes cost/latency impact.

## What is included

- `telemetry-simulator`: generates metrics for services and nodes.
- `collector`: ingests telemetry, writes to TimescaleDB, publishes to stream.
- `predictor`: LSTM forecasting service with heuristic fallback.
- `optimizer`: MILP scheduler (OR-Tools) with pod packing and spot-risk guardrails.
- `simulator`: queueing-based latency estimator.
- `decision`: predictive hybrid HPA+VPA orchestration with risk-aware downscale guardrail, shadow/canary/rollback rollout plan, and multi-cluster policy profiles.
- `dashboard`: real-time UI with what-if analysis.

## Architecture

`telemetry-simulator -> collector -> (timescaledb + kafka) -> predictor/optimizer/simulator -> decision -> dashboard`

## FAANG hardening features implemented

- Reliability rollout policy: shadow/canary/rollback gates via `GET /rollout/{service}`.
- Online learning loop hooks: retrain + model registry metadata script (`scripts/retrain_register.py`).
- Multi-cluster decision support: cluster profiles (`default`, `dev-cluster`, `prod-cluster`, `gpu-cluster`).
- Evaluation framework:
  - baseline-vs-MILP benchmark (`scripts/benchmark_baseline_vs_milp.py`)
  - rollout backtest (`scripts/backtest_rollout_policy.py`)
- Observability foundation: request-id middleware + structured decision logs.

## Quick start

Requirements:

- Docker + Docker Compose

Run default profile:

```bash
make up
```

Run scale profile (200 services / 500 nodes):

```bash
make up-scale
```

Open:

- Dashboard: `http://localhost:8080`
- Decision API: `http://localhost:8005/docs`
- Predictor API: `http://localhost:8002/docs`
- Optimizer API: `http://localhost:8003/docs`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Stop:

```bash
make down
```

## Key API examples

- Build recommendation: `GET /decision/{service}?cluster=prod-cluster`
- What-if scenario: `GET /what_if/{service}?traffic_multiplier=1.3&cluster=prod-cluster`
- Rollout gate decision: `GET /rollout/{service}?cluster=prod-cluster`
- Generate infra patches (Deployment + VPA + Terraform): `GET /artifacts/{service}?traffic_multiplier=1.2&cluster=prod-cluster`

## Training and evaluation commands

```bash
make retrain
make bench
make backtest
```

Outputs:

- `benchmark_report.json`
- `rollout_backtest_report.json`
- `services/predictor/checkpoints/model_registry.json`

## Design docs

- `docs/architecture.md`
- `docs/architecture-v2.md`
- `docs/system-design.md`
