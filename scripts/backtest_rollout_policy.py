#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import urllib.parse
import urllib.request


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(args: argparse.Namespace) -> None:
    decision = args.decision_url.rstrip("/")
    clusters = [c.strip() for c in args.clusters.split(",") if c.strip()]
    services = [f"service-{i:02d}" for i in range(1, args.limit + 1)]

    records = []
    for cluster in clusters:
        for service in services:
            url = f"{decision}/what_if/{urllib.parse.quote(service)}?traffic_multiplier={args.traffic_multiplier}&cluster={urllib.parse.quote(cluster)}"
            d = get_json(url)
            policy = d.get("policy", {})
            impact = d.get("impact", {})
            baseline = d.get("baseline", {})
            records.append(
                {
                    "cluster": cluster,
                    "service": service,
                    "stage": policy.get("rollout", {}).get("stage"),
                    "apply_allowed": policy.get("rollout", {}).get("apply_allowed", False),
                    "rollback_required": policy.get("rollout", {}).get("rollback_required", False),
                    "risk": impact.get("risk"),
                    "p95": float(impact.get("estimated_p95_latency_ms", 0.0)),
                    "savings_vs_current_pct": float(impact.get("estimated_cost_delta_pct", 0.0)),
                    "savings_vs_reactive_pct": float(baseline.get("optimizer_savings_vs_reactive_pct", 0.0)),
                }
            )

    if not records:
        raise SystemExit("no records")

    apply_rate = sum(1 for r in records if r["apply_allowed"]) / len(records)
    rollback_rate = sum(1 for r in records if r["rollback_required"]) / len(records)
    high_risk_rate = sum(1 for r in records if r["risk"] in {"high", "overloaded"}) / len(records)
    avg_p95 = statistics.mean(r["p95"] for r in records)
    avg_save_current = statistics.mean(r["savings_vs_current_pct"] for r in records)
    avg_save_reactive = statistics.mean(r["savings_vs_reactive_pct"] for r in records)

    print("=== Rollout Backtest Summary ===")
    print(f"clusters: {','.join(clusters)}")
    print(f"services_per_cluster: {args.limit}")
    print(f"traffic_multiplier: {args.traffic_multiplier}")
    print(f"apply_allowed_rate: {apply_rate:.3f}")
    print(f"rollback_required_rate: {rollback_rate:.3f}")
    print(f"high_risk_rate: {high_risk_rate:.3f}")
    print(f"avg_estimated_p95_ms: {avg_p95:.2f}")
    print(f"avg_savings_vs_current_pct: {avg_save_current:.2f}")
    print(f"avg_savings_vs_reactive_pct: {avg_save_reactive:.2f}")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump({"summary": {
                "apply_allowed_rate": apply_rate,
                "rollback_required_rate": rollback_rate,
                "high_risk_rate": high_risk_rate,
                "avg_estimated_p95_ms": avg_p95,
                "avg_savings_vs_current_pct": avg_save_current,
                "avg_savings_vs_reactive_pct": avg_save_reactive,
            }, "records": records}, f, indent=2)
        print(f"wrote: {args.output_json}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest rollout policy over multiple clusters")
    parser.add_argument("--decision-url", default="http://localhost:8005")
    parser.add_argument("--clusters", default="default,prod-cluster,dev-cluster")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--traffic-multiplier", type=float, default=1.2)
    parser.add_argument("--output-json", default="")
    run(parser.parse_args())
