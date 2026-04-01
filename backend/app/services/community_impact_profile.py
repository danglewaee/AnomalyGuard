from copy import deepcopy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import settings


_PROFILE_DIRECTORY = Path(__file__).resolve().parents[3] / "deployment" / "community-impact"
_DEFAULT_PROFILE_PATH = _PROFILE_DIRECTORY / "default.json"
_FALLBACK_PROFILE = {
    "display_name": "Default Community Profile",
    "description": "Balanced public-safe messaging for general downstream communities and shared water-dependent sites.",
    "corridor_template": "communities and water-dependent sites connected to {region}",
    "base_impacted_groups": ["Households", "Schools and care sites", "Water-dependent livelihoods"],
    "base_priority_sites": ["Untreated intake points", "Schools and clinics", "Storage and refill points"],
    "default_impact_copy": "Operators should keep updates focused on untreated intake, public-service sites, and water-dependent livelihoods.",
    "signal_rules": [],
}


def _normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = dict(_FALLBACK_PROFILE)
    profile.update(raw)
    profile["display_name"] = str(profile.get("display_name") or _FALLBACK_PROFILE["display_name"])
    profile["description"] = str(profile.get("description") or _FALLBACK_PROFILE["description"])
    profile["base_impacted_groups"] = list(profile.get("base_impacted_groups") or _FALLBACK_PROFILE["base_impacted_groups"])
    profile["base_priority_sites"] = list(profile.get("base_priority_sites") or _FALLBACK_PROFILE["base_priority_sites"])
    profile["signal_rules"] = list(profile.get("signal_rules") or [])
    profile["corridor_template"] = str(profile.get("corridor_template") or _FALLBACK_PROFILE["corridor_template"])
    profile["default_impact_copy"] = str(profile.get("default_impact_copy") or _FALLBACK_PROFILE["default_impact_copy"])
    return profile


def _default_display_name(profile_key: str) -> str:
    return profile_key.replace("-", " ").title()


def _configured_or_default_profile_path() -> Path:
    configured_path = settings.community_impact_profile_path.strip()
    candidate = Path(configured_path).expanduser() if configured_path else _DEFAULT_PROFILE_PATH
    return candidate if candidate.exists() else _DEFAULT_PROFILE_PATH


def _profile_key_for_path(candidate: Path) -> str:
    try:
        if candidate.resolve().parent == _PROFILE_DIRECTORY.resolve():
            return candidate.stem
    except OSError:
        pass
    return "custom"


@lru_cache(maxsize=16)
def _load_profile_from_path(path_str: str) -> dict[str, Any]:
    candidate = Path(path_str)
    try:
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _normalize_profile(_FALLBACK_PROFILE)

    if not isinstance(raw, dict):
        return _normalize_profile(_FALLBACK_PROFILE)

    return _normalize_profile(raw)


def _profile_option_from_path(candidate: Path) -> dict[str, Any]:
    profile_key = _profile_key_for_path(candidate)
    profile = deepcopy(_load_profile_from_path(str(candidate)))
    return {
        "key": profile_key,
        "display_name": str(profile.get("display_name") or _default_display_name(profile_key)),
        "description": str(profile.get("description") or ""),
        "is_default": candidate.resolve() == _DEFAULT_PROFILE_PATH.resolve(),
    }


def load_community_impact_profile(profile_key: str | None = None) -> tuple[str, dict[str, Any]]:
    if profile_key:
        if profile_key == "custom":
            candidate = _configured_or_default_profile_path()
        else:
            candidate = _PROFILE_DIRECTORY / f"{profile_key}.json"
            if not candidate.exists():
                raise ValueError(f"Unknown community impact profile: {profile_key}")
    else:
        candidate = _configured_or_default_profile_path()

    resolved_key = _profile_key_for_path(candidate)
    return resolved_key, deepcopy(_load_profile_from_path(str(candidate)))


def active_community_impact_profile_option() -> dict[str, Any]:
    return _profile_option_from_path(_configured_or_default_profile_path())


def list_community_impact_profiles() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    if _PROFILE_DIRECTORY.exists():
        profiles = [_profile_option_from_path(candidate) for candidate in sorted(_PROFILE_DIRECTORY.glob("*.json"))]

    active_profile = active_community_impact_profile_option()
    if active_profile["key"] == "custom" and not any(item["key"] == "custom" for item in profiles):
        profiles.insert(0, active_profile)

    profiles.sort(key=lambda item: (not item["is_default"], item["display_name"]))
    return profiles
