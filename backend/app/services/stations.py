from app.schemas import StationProfile

STATION_PROFILES: dict[str, StationProfile] = {
    "mekong-can-tho": StationProfile(
        station_id="mekong-can-tho",
        station_name="Can Tho River Gate",
        region="Can Tho, Mekong Delta",
        timezone="Asia/Ho_Chi_Minh",
        latitude=10.0452,
        longitude=105.7469,
        source="simulated",
    ),
    "saigon-thu-duc": StationProfile(
        station_id="saigon-thu-duc",
        station_name="Thu Duc Intake",
        region="Thu Duc, Ho Chi Minh City",
        timezone="Asia/Ho_Chi_Minh",
        latitude=10.8480,
        longitude=106.7720,
        source="simulated",
    ),
    "red-river-ha-noi": StationProfile(
        station_id="red-river-ha-noi",
        station_name="Long Bien Monitoring Point",
        region="Long Bien, Ha Noi",
        timezone="Asia/Ho_Chi_Minh",
        latitude=21.0409,
        longitude=105.8804,
        source="simulated",
    ),
}


def list_stations() -> list[StationProfile]:
    return list(STATION_PROFILES.values())


def get_station(station_id: str) -> StationProfile:
    return STATION_PROFILES[station_id]


def has_station(station_id: str) -> bool:
    return station_id in STATION_PROFILES


def register_station(profile: StationProfile) -> StationProfile:
    STATION_PROFILES[profile.station_id] = profile
    return profile


def default_station_id() -> str:
    return "mekong-can-tho"
