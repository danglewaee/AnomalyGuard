from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="decision")

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://localhost:8001")
PREDICTOR_URL = os.getenv("PREDICTOR_URL", "http://localhost:8002")
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", "http://localhost:8003")
SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://localhost:8004")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("decision")

INSTANCE_CAPACITY = {
    "m5.large": 220.0,
    "m5a.large": 205.0,
    "c6i.large": 260.0,
    "spot-gpu-small": 420.0,
}
INSTANCE_HOURLY_COST = {
    "m5.large": 0.096,
    "m5a.large": 0.086,
    "c6i.large": 0.102,
    "spot-gpu-small": 0.11,
}

CLUSTER_PROFILES = {
    "dev-cluster": {"default_nodes": 6, "default_instance": "m5a.large", "latency_budget_ms": 240.0, "max_downscale_step": 3},
    "prod-cluster": {"default_nodes": 16, "default_instance": "c6i.large", "latency_budget_ms": 180.0, "max_downscale_step": 2},
    "gpu-cluster": {"default_nodes": 10, "default_instance": "spot-gpu-small", "latency_budget_ms": 200.0, "max_downscale_step": 2},
    "default": {"default_nodes": 12, "default_instance": "m5.large", "latency_budget_ms": 200.0, "max_downscale_step": 2},
}

FALLBACK_SERVICES = [f"service-{i:02d}" for i in range(1, 11)]


@app.middleware("http")
async def request_context(request: Request, call_next):
    req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = req_id
    started = datetime.now(timezone.utc)
    response = await call_next(request)
    elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
    response.headers["x-request-id"] = req_id
    logger.info("request path=%s method=%s status=%s elapsed_ms=%.2f request_id=%s", request.url.path, request.method, response.status_code, elapsed_ms, req_id)
    return response


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled_error request_id=%s path=%s err=%s", req_id, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "internal_server_error", "request_id": req_id, "detail": str(exc)})


def _safe_name(service: str) -> str:
    return service.lower().replace("_", "-")


def _seed(service: str, cluster: str) -> int:
    return sum(ord(c) for c in (service + cluster))


def _cluster_profile(cluster: str) -> dict[str, Any]:
    return CLUSTER_PROFILES.get(cluster, CLUSTER_PROFILES["default"])


def _fallback_forecast(service: str, cluster: str, horizon_min: int) -> dict[str, Any]:
    rnd = random.Random(_seed(service, cluster) + horizon_min)
    base = 95 + (horizon_min * 0.9)
    burst = 20 if cluster == "prod-cluster" else 0
    rps = max(10.0, base + burst + rnd.uniform(-20, 24))
    cpu = max(15.0, min(95.0, 38 + (rps / 5.3) + rnd.uniform(-8, 8)))
    return {
        "service": service,
        "cluster": cluster,
        "horizon_min": horizon_min,
        "pred_rps": round(rps, 2),
        "pred_cpu_pct": round(cpu, 2),
        "confidence": 0.55,
        "model_source": "fallback",
    }


def _fallback_latest(service: str, cluster: str) -> dict[str, Any]:
    rnd = random.Random(_seed(service, cluster))
    profile = _cluster_profile(cluster)
    return {
        "service": service,
        "cluster": cluster,
        "rps": round(100 + rnd.uniform(-20, 20), 2),
        "p95_latency_ms": round(profile["latency_budget_ms"] * 0.5 + rnd.uniform(-12, 22), 2),
        "cpu_pct": round(55 + rnd.uniform(-10, 12), 2),
    }


def _vertical_requests(pred_cpu_pct: float) -> tuple[int, int]:
    cpu_m = int(max(100, min(1400, 120 + pred_cpu_pct * 7)))
    mem_mi = int(max(256, min(4096, 384 + pred_cpu_pct * 15)))
    return cpu_m, mem_mi


def build_k8s_patch(service: str, nodes: int, cpu_m: int, mem_mi: int) -> str:
    dep_name = _safe_name(service)
    return (
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "metadata:\n"
        f"  name: {dep_name}\n"
        "spec:\n"
        f"  replicas: {nodes}\n"
        "  template:\n"
        "    spec:\n"
        "      containers:\n"
        "      - name: app\n"
        "        resources:\n"
        "          requests:\n"
        f"            cpu: \"{cpu_m}m\"\n"
        f"            memory: \"{mem_mi}Mi\"\n"
        "          limits:\n"
        f"            cpu: \"{int(cpu_m * 2)}m\"\n"
        f"            memory: \"{int(mem_mi * 2)}Mi\"\n"
    )


def build_vpa_patch(service: str, cpu_m: int, mem_mi: int) -> str:
    dep_name = _safe_name(service)
    return (
        "apiVersion: autoscaling.k8s.io/v1\n"
        "kind: VerticalPodAutoscaler\n"
        "metadata:\n"
        f"  name: {dep_name}-vpa\n"
        "spec:\n"
        "  targetRef:\n"
        "    apiVersion: apps/v1\n"
        "    kind: Deployment\n"
        f"    name: {dep_name}\n"
        "  updatePolicy:\n"
        "    updateMode: \"Auto\"\n"
    )


def build_terraform_patch(service: str, instance_type: str, nodes: int, cluster: str) -> str:
    mod_name = _safe_name(service).replace("-", "_")
    return (
        f"module \"{mod_name}_autoscaling\" {{\n"
        "  source        = \"./modules/node_group\"\n"
        f"  cluster_name  = \"{cluster}\"\n"
        f"  service_name  = \"{service}\"\n"
        f"  instance_type = \"{instance_type}\"\n"
        f"  desired_nodes = {nodes}\n"
        "}\n"
    )


def _baseline_reactive_plan(pred_rps: float, instance_type: str, latency_budget_ms: float) -> tuple[int, float]:
    cap = INSTANCE_CAPACITY.get(instance_type, 220.0)
    util_cap = 0.75 if latency_budget_ms <= 200 else 0.82
    nodes = max(1, int((pred_rps * 1.2) / max(cap * util_cap, 1)) + 1)
    hourly_cost = nodes * INSTANCE_HOURLY_COST.get(instance_type, 0.096)
    return nodes, hourly_cost


def _rollout_plan(current_nodes: int, target_nodes: int, max_downscale_step: int, risk: str, predicted_p95: float, latency_budget_ms: float) -> dict[str, Any]:
    candidate_downscale = target_nodes < current_nodes
    rollback = risk in {"high", "overloaded"} or predicted_p95 > latency_budget_ms

    if candidate_downscale and (current_nodes - target_nodes) > max_downscale_step:
        return {
            "stage": "shadow",
            "reason": "downscale_step_too_large",
            "apply_allowed": False,
            "rollback_required": False,
        }

    if rollback:
        return {
            "stage": "rollback",
            "reason": "slo_risk_violation",
            "apply_allowed": False,
            "rollback_required": True,
        }

    return {
        "stage": "canary",
        "reason": "candidate_safe_for_canary",
        "apply_allowed": True,
        "rollback_required": False,
        "canary_replicas": max(1, int(target_nodes * 0.2)),
        "full_rollout_replicas": target_nodes,
    }


async def _try_forecast(client: httpx.AsyncClient, service: str, cluster: str, horizon_min: int) -> dict[str, Any]:
    try:
        resp = await client.get(f"{PREDICTOR_URL}/forecast/{service}", params={"horizon_min": horizon_min})
        resp.raise_for_status()
        body = resp.json()
        body["cluster"] = cluster
        return body
    except Exception:
        return _fallback_forecast(service, cluster, horizon_min)


async def _try_latest(client: httpx.AsyncClient, service: str, cluster: str) -> dict[str, Any]:
    try:
        resp = await client.get(f"{COLLECTOR_URL}/latest", params={"service": service})
        resp.raise_for_status()
        event = (resp.json() or {}).get("event")
        if event:
            event["cluster"] = cluster
            return event
        return _fallback_latest(service, cluster)
    except Exception:
        return _fallback_latest(service, cluster)


async def _try_services(client: httpx.AsyncClient, limit: int) -> list[str]:
    try:
        resp = await client.get(f"{COLLECTOR_URL}/services")
        resp.raise_for_status()
        services = (resp.json() or {}).get("services", [])
        return services[:limit] if services else FALLBACK_SERVICES[:limit]
    except Exception:
        return FALLBACK_SERVICES[:limit]


async def build_decision(service: str, traffic_multiplier: float = 1.0, cluster: str = "default") -> dict[str, Any]:
    effective_multiplier = max(0.1, traffic_multiplier)
    profile = _cluster_profile(cluster)

    async with httpx.AsyncClient(timeout=10.0) as client:
        forecast_5 = await _try_forecast(client, service, cluster, 5)
        forecast_15 = await _try_forecast(client, service, cluster, 15)
        forecast_60 = await _try_forecast(client, service, cluster, 60)
        latest = await _try_latest(client, service, cluster)

        base_rps_15 = float(forecast_15["pred_rps"])
        surge_rps_60 = float(forecast_60["pred_rps"])
        planning_rps = max(base_rps_15, surge_rps_60 * 0.9) * effective_multiplier

        current_nodes = int(profile["default_nodes"])
        current_instance = str(profile["default_instance"])
        latency_budget_ms = float(profile["latency_budget_ms"])
        current_rps = float(latest.get("rps", planning_rps))

        opt_resp = await client.post(
            f"{OPTIMIZER_URL}/optimize",
            json={
                "service": service,
                "current_nodes": current_nodes,
                "pred_rps": planning_rps,
                "latency_budget_ms": latency_budget_ms,
                "current_instance_type": current_instance,
            },
        )
        opt_resp.raise_for_status()
        opt = opt_resp.json()

        rec_nodes = int(opt.get("target_nodes", current_nodes))
        rec_type = opt.get("target_instance_type", current_instance)

        predicted_cpu_pct = float(forecast_15.get("pred_cpu_pct", latest.get("cpu_pct", 55.0)))
        cpu_m, mem_mi = _vertical_requests(predicted_cpu_pct)

        cap = INSTANCE_CAPACITY.get(rec_type, 220.0)
        sim_main = await client.post(
            f"{SIMULATOR_URL}/simulate",
            json={
                "nodes": rec_nodes,
                "expected_rps": planning_rps,
                "per_node_capacity_rps": cap,
                "base_latency_ms": float(latest.get("p95_latency_ms", 90.0)),
            },
        )
        sim_main.raise_for_status()
        sim = sim_main.json()

        guardrail_triggered = False
        guardrail_reason = ""
        if rec_nodes < current_nodes:
            surge_resp = await client.post(
                f"{SIMULATOR_URL}/simulate",
                json={
                    "nodes": rec_nodes,
                    "expected_rps": planning_rps * 1.2,
                    "per_node_capacity_rps": cap,
                    "base_latency_ms": float(latest.get("p95_latency_ms", 90.0)),
                },
            )
            surge_resp.raise_for_status()
            surge_sim = surge_resp.json()
            if surge_sim.get("risk") in {"high", "overloaded"} or float(surge_sim["predicted_p95_latency_ms"]) > latency_budget_ms:
                guardrail_triggered = True
                guardrail_reason = "downscale_blocked_by_surge_risk"
                rec_nodes = current_nodes
                rec_type = current_instance
                sim = {
                    "predicted_p95_latency_ms": float(latest.get("p95_latency_ms", 90.0)),
                    "risk": "medium",
                }

        current_cost_hourly = INSTANCE_HOURLY_COST[current_instance] * current_nodes
        optimized_hourly_cost = float(opt.get("estimated_hourly_cost") or current_cost_hourly)
        if guardrail_triggered:
            optimized_hourly_cost = INSTANCE_HOURLY_COST[rec_type] * rec_nodes

        baseline_nodes, baseline_cost = _baseline_reactive_plan(planning_rps, current_instance, latency_budget_ms)
        baseline_savings_pct = ((baseline_cost - optimized_hourly_cost) / baseline_cost) * 100 if baseline_cost else 0.0

        cost_delta_pct = ((current_cost_hourly - optimized_hourly_cost) / current_cost_hourly) * 100 if current_cost_hourly else 0.0
        risk = sim.get("risk", "low")
        risk_score = 0.2 if risk == "low" else (0.5 if risk == "medium" else 0.8)

        rollout = _rollout_plan(
            current_nodes=current_nodes,
            target_nodes=rec_nodes,
            max_downscale_step=int(profile["max_downscale_step"]),
            risk=risk,
            predicted_p95=float(sim.get("predicted_p95_latency_ms", 90.0)),
            latency_budget_ms=latency_budget_ms,
        )

        return {
            "service": service,
            "cluster": cluster,
            "policy": {
                "mode": "predictive_hybrid_hpa_vpa",
                "downscale_guardrail_triggered": guardrail_triggered,
                "guardrail_reason": guardrail_reason,
                "rollout": rollout,
            },
            "scenario": {
                "traffic_multiplier": round(effective_multiplier, 2),
                "base_predicted_rps_5m": round(float(forecast_5["pred_rps"]), 2),
                "base_predicted_rps_15m": round(base_rps_15, 2),
                "base_predicted_rps_60m": round(surge_rps_60, 2),
                "planning_predicted_rps": round(planning_rps, 2),
                "model_source": forecast_15.get("model_source", "fallback"),
            },
            "current": {
                "nodes": current_nodes,
                "instance_type": current_instance,
                "rps": round(current_rps, 2),
                "hourly_cost": round(current_cost_hourly, 4),
            },
            "baseline": {
                "reactive_nodes": baseline_nodes,
                "reactive_hourly_cost": round(baseline_cost, 4),
                "optimizer_savings_vs_reactive_pct": round(baseline_savings_pct, 2),
            },
            "recommended": {
                "nodes": rec_nodes,
                "instance_type": rec_type,
                "predicted_rps_30m": round(planning_rps, 2),
                "allocation": opt.get("allocation", []),
                "spot_ratio": opt.get("spot_ratio", 0.0),
                "vertical": {"cpu_request_m": cpu_m, "memory_request_mi": mem_mi},
            },
            "impact": {
                "estimated_cost_delta_pct": round(cost_delta_pct, 2),
                "estimated_hourly_cost": round(optimized_hourly_cost, 4),
                "estimated_p95_latency_ms": sim.get("predicted_p95_latency_ms", 90.0),
                "risk": risk,
                "risk_score": risk_score,
            },
            "constraints": opt.get("constraints", {}),
            "optimizer_error": opt.get("error"),
            "artifacts": {
                "kubernetes_patch": build_k8s_patch(service, rec_nodes, cpu_m, mem_mi),
                "kubernetes_vpa_patch": build_vpa_patch(service, cpu_m, mem_mi),
                "terraform_patch": build_terraform_patch(service, rec_type, rec_nodes, cluster),
            },
        }


@app.get("/decision/{service}")
async def decision(service: str, cluster: str = "default") -> dict[str, Any]:
    return await build_decision(service, cluster=cluster)


@app.get("/decision_all")
async def decision_all(limit: int = 10, cluster: str = "default") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        services = await _try_services(client, limit)
    return {"cluster": cluster, "decisions": [await build_decision(s, cluster=cluster) for s in services]}


@app.get("/what_if/{service}")
async def what_if(service: str, traffic_multiplier: float = 1.3, cluster: str = "default") -> dict[str, Any]:
    return await build_decision(service, traffic_multiplier=traffic_multiplier, cluster=cluster)


@app.get("/what_if_all")
async def what_if_all(traffic_multiplier: float = 1.3, limit: int = 10, cluster: str = "default") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        services = await _try_services(client, limit)
    return {
        "cluster": cluster,
        "traffic_multiplier": traffic_multiplier,
        "decisions": [await build_decision(s, traffic_multiplier=traffic_multiplier, cluster=cluster) for s in services],
    }


@app.get("/artifacts/{service}")
async def artifacts(service: str, traffic_multiplier: float = 1.0, cluster: str = "default") -> dict[str, Any]:
    d = await build_decision(service, traffic_multiplier=traffic_multiplier, cluster=cluster)
    return {
        "service": service,
        "cluster": cluster,
        "traffic_multiplier": traffic_multiplier,
        "policy": d.get("policy", {}),
        "recommended": d.get("recommended", {}),
        "artifacts": d.get("artifacts", {}),
    }


@app.get("/rollout/{service}")
async def rollout(service: str, cluster: str = "default", traffic_multiplier: float = 1.0) -> dict[str, Any]:
    d = await build_decision(service, traffic_multiplier=traffic_multiplier, cluster=cluster)
    return {
        "service": service,
        "cluster": cluster,
        "policy": d.get("policy", {}),
        "impact": d.get("impact", {}),
        "baseline": d.get("baseline", {}),
    }


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
