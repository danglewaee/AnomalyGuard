# System Design Roadmap (Level C, FAANG Hardening)

## Axis 1: Reliability-first Rollout

- [x] Shadow/Canary/Rollback policy endpoint (`GET /rollout/{service}`)
- [x] Surge-aware downscale guardrail (+20% traffic check)
- [ ] Integrate Argo Rollouts for live canary execution

## Axis 2: Online Learning Loop

- [x] Retrain-and-register script (`scripts/retrain_register.py`)
- [x] Model registry endpoint (`GET /model/registry`)
- [ ] Drift detection + auto rollback to previous model

## Axis 3: Multi-Cluster Control

- [x] Cluster profile-aware decisions (`cluster` query parameter)
- [x] Cluster-aware Terraform patch generation
- [ ] Global optimizer across clusters with quota constraints

## Axis 4: Strong Evaluation Framework

- [x] Baseline-vs-MILP benchmark with SLO metrics (`benchmark_baseline_vs_milp.py`)
- [x] Rollout backtesting script (`backtest_rollout_policy.py`)
- [ ] CI benchmark publish and trend tracking

## Axis 5: Production Engineering Quality

- [x] Request-id middleware + structured logs
- [ ] OpenTelemetry traces and metrics export
- [ ] Chaos test suite (predictor/optimizer/simulator failure injection)

## Suggested KPIs

- Cost reduction vs reactive baseline: `>= 20%`
- Latency SLO violation rate: `< 1%`
- Rollback trigger rate under normal load: `< 5%`
- Decision API latency: `p95 < 3s`
- Ingestion throughput (target): `>= 100k metrics/min`
