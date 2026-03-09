# Architecture

## Services

- `telemetry-simulator`: generates service/node telemetry.
- `collector`: ingests telemetry, persists to TimescaleDB, emits stream events.
- `predictor`: LSTM forecasting (`rps`, `cpu`) with heuristic fallback.
- `optimizer`: MILP-based scheduler with cost, latency, pod packing, and spot-risk constraints.
- `simulator`: queueing-style latency risk simulation.
- `decision`: predictive hybrid HPA+VPA orchestrator with request-id logging, rollout policy gating, and patch artifacts.
- `dashboard`: realtime and what-if UI.

## Optimization and Rollout Flow

1. Predictor forecasts demand for horizons 5m, 15m, and 60m.
2. Decision layer computes planning demand and calls MILP optimizer.
3. Optimizer solves node mix with throughput, latency-utilization, pod packing, and spot ratio constraints.
4. Simulator validates expected latency and risk.
5. Downscale guardrail runs surge (+20%) check before allowing downscale.
6. Rollout policy selects `shadow`, `canary`, or `rollback`.
7. Decision API returns final recommendation + impact + infrastructure patches.

## Multi-Cluster Profiles

- `default`
- `dev-cluster`
- `prod-cluster`
- `gpu-cluster`

Each profile defines default node count, instance class, latency budget, and max downscale step.

## Decision Outputs

- Horizontal decision: `recommended.nodes`, `recommended.instance_type`
- Vertical decision: `recommended.vertical.cpu_request_m`, `recommended.vertical.memory_request_mi`
- Rollout gate: `policy.rollout.stage`, `policy.rollout.apply_allowed`, `policy.rollout.rollback_required`
- Baseline comparison: `baseline.optimizer_savings_vs_reactive_pct`
- Artifacts: Kubernetes deployment patch, VPA patch, Terraform module snippet

## Observability

- Request correlation: `x-request-id` middleware.
- Structured logs on each decision request with elapsed time.
