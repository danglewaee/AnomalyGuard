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
        community_name="Can Tho Riverside Communities",
        province="Can Tho",
        water_use_type="mixed",
        population_served=125000,
        households_served=26500,
        schools_nearby=18,
        critical_assets=["household intake points", "primary schools", "aquaculture ponds"],
        escalation_contacts=["district water operator", "commune health officer"],
        notification_endpoints=[
            {
                "role": "duty-operator",
                "channel": "email",
                "address": "ops-cantho@example.org",
                "label": "Can Tho duty operator",
                "min_risk_level": "low",
            },
            {
                "role": "public-health",
                "channel": "sms",
                "address": "+84900000001",
                "label": "Can Tho commune health officer",
                "min_risk_level": "high",
            },
            {
                "role": "community-response",
                "channel": "webhook",
                "address": "https://example.org/hooks/cantho-community-response",
                "label": "Can Tho response automation",
                "min_risk_level": "critical",
            },
        ],
        exposure_notes="Dense riverside communities depend on surface water and small-scale treatment.",
    ),
    "saigon-thu-duc": StationProfile(
        station_id="saigon-thu-duc",
        station_name="Thu Duc Intake",
        region="Thu Duc, Ho Chi Minh City",
        timezone="Asia/Ho_Chi_Minh",
        latitude=10.8480,
        longitude=106.7720,
        source="simulated",
        community_name="Thu Duc Intake Service Zone",
        province="Ho Chi Minh City",
        water_use_type="drinking",
        population_served=210000,
        households_served=46500,
        schools_nearby=24,
        critical_assets=["municipal intake", "schools", "community clinics"],
        escalation_contacts=["city water utility shift lead", "district public health desk"],
        notification_endpoints=[
            {
                "role": "duty-operator",
                "channel": "email",
                "address": "ops-thuduc@example.org",
                "label": "Thu Duc utility shift lead",
                "min_risk_level": "low",
            },
            {
                "role": "public-health",
                "channel": "sms",
                "address": "+84900000002",
                "label": "Thu Duc public health desk",
                "min_risk_level": "high",
            },
            {
                "role": "community-response",
                "channel": "webhook",
                "address": "https://example.org/hooks/thuduc-water-response",
                "label": "Thu Duc response automation",
                "min_risk_level": "critical",
            },
        ],
        exposure_notes="Urban households and schools depend on intake continuity and water quality stability.",
    ),
    "red-river-ha-noi": StationProfile(
        station_id="red-river-ha-noi",
        station_name="Long Bien Monitoring Point",
        region="Long Bien, Ha Noi",
        timezone="Asia/Ho_Chi_Minh",
        latitude=21.0409,
        longitude=105.8804,
        source="simulated",
        community_name="Long Bien River-edge Communities",
        province="Ha Noi",
        water_use_type="mixed",
        population_served=98000,
        households_served=21400,
        schools_nearby=12,
        critical_assets=["irrigation intakes", "residential supply points", "nearby schools"],
        escalation_contacts=["river operations desk", "ward disaster response lead"],
        notification_endpoints=[
            {
                "role": "duty-operator",
                "channel": "email",
                "address": "ops-longbien@example.org",
                "label": "Long Bien river operations desk",
                "min_risk_level": "low",
            },
            {
                "role": "public-health",
                "channel": "sms",
                "address": "+84900000003",
                "label": "Long Bien ward response lead",
                "min_risk_level": "high",
            },
        ],
        exposure_notes="Mixed residential and peri-urban agriculture exposure downstream of the monitoring point.",
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
