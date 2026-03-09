# System Design Roadmap (Level C, Tech Stack v2)

## Phase 1: Stabilize Current MVP

- [x] LSTM predictor
- [x] MILP optimizer with spot-risk and pod packing
- [x] What-if scenario API
- [x] Baseline-vs-MILP benchmark harness

## Phase 2: Protocol + Policy Foundation

- [ ] Introduce gRPC + Protobuf for internal service calls
- [ ] Add OPA/Rego policy gate (`policy-evaluator`)
- [ ] Define CRDs (`AutopilotPolicy`, `AutopilotPlan`)

## Phase 3: Kubernetes-Native Control Plane (Go)

- [ ] Implement `autopilot-agent` (Go)
- [ ] Implement `autopilot-controller` (Go)
- [ ] Integrate Argo Rollouts for canary and rollback

## Phase 4: Stream/Storage Scale Upgrade

- [ ] Add Flink streaming feature jobs
- [ ] Add ClickHouse analytics store
- [ ] Keep TimescaleDB for operational horizon

## Phase 5: Ingestion Throughput Upgrade (Rust)

- [ ] Build `telemetry-gateway` in Rust
- [ ] Hit and publish 100k+ metrics/min benchmark report
- [ ] Add backpressure + retry semantics validation

## Phase 6: Open-Source Productization

- [ ] Split modules into `autopilot-*` packages
- [ ] Add Helm chart install path
- [ ] Add CI benchmark and demo artifacts

## Suggested KPIs

- Cost reduction vs baseline: `>= 20%`
- Latency constraint violation rate: `< 1%`
- Optimizer solve time: `p95 < 1s` (200 services / 500 nodes)
- Decision API latency: `p95 < 3s`
- Ingestion throughput: `>= 100k metrics/min`
