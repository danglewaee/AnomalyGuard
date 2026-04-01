from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import CommunityImpactProfilesResponse, CommunityOverview
from app.services.community_impact_profile import active_community_impact_profile_option, list_community_impact_profiles
from app.services.community_summary import build_community_overview
from app.services.stations import list_stations
from app.services.store_pg import PostgresStore


router = APIRouter()


@router.get("/api/community/overview", response_model=CommunityOverview)
def community_overview(
    since_minutes: int = Query(default=720, ge=60, le=10080),
    impact_profile: str | None = Query(default=None, min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> dict:
    store = PostgresStore(db)
    try:
        overview = build_community_overview(
            alerts=store.latest_alerts(limit=300, since_minutes=since_minutes),
            readings=store.latest_readings(limit=1000, since_minutes=since_minutes),
            stations=list_stations(),
            since_minutes=since_minutes,
            impact_profile_key=impact_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return overview.model_dump(mode="json")


@router.get("/api/community/impact-profiles", response_model=CommunityImpactProfilesResponse)
def community_impact_profiles() -> dict:
    active_profile = active_community_impact_profile_option()
    return {
        "active_profile": active_profile["key"],
        "profiles": list_community_impact_profiles(),
    }
