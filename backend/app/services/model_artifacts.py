import re

from app.config import settings
from app.schemas import ModelArtifactDescriptor, RetrainingManifestResponse


_TOKEN_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def _slug_token(value: str, fallback: str) -> str:
    token = _TOKEN_PATTERN.sub("-", (value or "").strip()).strip("-._").lower()
    return token or fallback


def build_model_artifact_descriptor(
    *,
    manifest: RetrainingManifestResponse,
    mlflow_run_id: str,
    run_name: str,
) -> ModelArtifactDescriptor:
    artifact_key = _slug_token(settings.model_artifact_key, "anomalyguard-anomaly-detector")
    source_revision = _slug_token(settings.model_source_revision or settings.app_version, "dev")
    artifact_version = f"{source_revision}-{manifest.fingerprint[:12]}"
    candidate_id = f"{artifact_key}-{artifact_version}"
    artifact_uri = f"mlflow://runs/{mlflow_run_id}" if mlflow_run_id else f"bundle://{run_name or candidate_id}"
    return ModelArtifactDescriptor(
        candidate_id=candidate_id,
        artifact_key=artifact_key,
        artifact_version=artifact_version,
        source_revision=source_revision,
        artifact_uri=artifact_uri,
        manifest_id=manifest.manifest_id,
        manifest_fingerprint=manifest.fingerprint,
    )


def read_model_artifact_descriptor(bundle: dict) -> ModelArtifactDescriptor:
    model_artifact = bundle.get("model_artifact") or {}
    manifest = bundle.get("manifest") or {}
    manifest_id = str(model_artifact.get("manifest_id") or manifest.get("manifest_id") or "").strip()
    manifest_fingerprint = str(model_artifact.get("manifest_fingerprint") or manifest.get("fingerprint") or "").strip()
    artifact_key = _slug_token(str(model_artifact.get("artifact_key") or settings.model_artifact_key), "anomalyguard-anomaly-detector")
    source_revision = _slug_token(
        str(model_artifact.get("source_revision") or settings.model_source_revision or settings.app_version),
        "dev",
    )
    artifact_version = _slug_token(
        str(model_artifact.get("artifact_version") or f"{source_revision}-{manifest_fingerprint[:12] or manifest_id[:12] or 'legacy'}"),
        "legacy",
    )
    candidate_id = _slug_token(
        str(model_artifact.get("candidate_id") or f"{artifact_key}-{artifact_version}"),
        "legacy-candidate",
    )
    artifact_uri = str(
        model_artifact.get("artifact_uri")
        or (f"mlflow://runs/{bundle.get('mlflow_run_id')}" if bundle.get("mlflow_run_id") else f"bundle://{bundle.get('run_name') or candidate_id}")
    ).strip()
    return ModelArtifactDescriptor(
        candidate_id=candidate_id,
        artifact_key=artifact_key,
        artifact_version=artifact_version,
        source_revision=source_revision,
        artifact_uri=artifact_uri,
        manifest_id=manifest_id,
        manifest_fingerprint=manifest_fingerprint,
    )
