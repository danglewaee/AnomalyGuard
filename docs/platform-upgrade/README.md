# Platform Upgrade

This folder captures the FAANG-grade upgrade path for `AnomalyGuard` without treating the current repo like throwaway demo code.

Files:

- `target-architecture.md`
  - target platform shape, service boundaries, data plane, ML plane, and observability model
- `migration-roadmap.md`
  - phased rollout from the current repo to the target platform
- `phase-1-foundation-backlog.md`
  - concrete work breakdown to start implementation without a big-bang rewrite
- `ci-cd-and-ops-playbook.md`
  - release gates, rollback rules, observability dashboards, and incident playbooks

Core rule:

- preserve the working product
- add seams first
- move from modular monolith to platform services deliberately
- do not introduce infrastructure that the repo cannot operate yet
