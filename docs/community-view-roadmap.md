# Community View Roadmap

This document turns `AnomalyGuard` from an operator-heavy anomaly dashboard into a community-facing early-warning platform for water risk.

The current codebase already has the right foundation:

- realtime readings and alerts
- VN data ingest and USGS ingest
- ESP32-compatible device telemetry
- operator control for edge devices
- websocket updates for live status

The next step is not to add random complexity. It is to focus the product around a clearer promise:

`Help local operators detect water risk early enough to protect nearby communities.`

## Product Direction

`AnomalyGuard` should support two distinct views:

- `Operator Console`: for technicians, station operators, and local response teams
- `Community View`: for citizens, schools, fish farmers, and local administrators who need simple, location-based risk updates

This split matters because the current UI is optimized for operators. It exposes metrics, control payloads, and ingest actions, but it does not yet explain impact in a way that helps a community decide what to do.

## Primary Users

- `Station operator`
  - watches telemetry, acknowledges incidents, and pushes device control
- `Local environmental officer`
  - monitors zones, verifies field reports, and coordinates response
- `Aquaculture owner`
  - needs simple warnings about intake risk, oxygen stress, and abnormal water behavior
- `Community member`
  - needs plain-language status, local map context, and clear next actions

## Best Technology Additions

These are the strongest additions because they are modern, defensible, and directly improve the product.

### 1. GeoAI with `PostGIS` plus `MapLibre`

Why it fits:

- water risk is spatial, not just numeric
- a map is more understandable than a chart for non-operators
- the repo already uses PostgreSQL, so `PostGIS` is a natural upgrade

What it unlocks:

- station-to-zone mapping
- affected community overlays
- downstream risk display
- school, intake, and aquaculture proximity awareness

Implementation:

- enable `PostGIS` on the existing database
- add tables for `community_zones`, `assets`, and `zone_station_links`
- use `MapLibre` or `Leaflet` for a community map view

### 2. Predictive Risk with `LightGBM` or `XGBoost`

Why it fits:

- the current detector is mostly reactive
- communities benefit more from early warning than from after-the-fact detection
- tree models are pragmatic, fast, and easier to operate than deep learning for this dataset size

What it unlocks:

- 6-hour, 12-hour, and 24-hour risk forecasts
- station-specific baselines
- fewer false positives than a single global ruleset

Implementation:

- keep the current anomaly detector as a fallback
- add a forecasting job using weather, discharge, telemetry, and seasonal features
- score `risk_level` per station and per zone

### 3. LLM Explain Layer

Why it fits:

- the project needs to become more human-readable
- community members do not reason in `pH`, `TDS`, or `turbidity` thresholds
- an LLM is useful here as an explanation layer, not the decision engine

What it unlocks:

- plain-language Vietnamese alert summaries
- recommended next actions per audience
- operator-to-community translation without manual rewriting

Implementation:

- generate structured alert facts first
- pass those facts into a guarded LLM prompt
- output short messages for `community`, `operator`, and `official` audiences

Rule:

- the LLM should never decide whether water is safe
- it should only explain model outputs and recommended actions already derived from system rules

### 4. Notification Integrations

Why it fits:

- a dashboard is not enough for community response
- alerts should reach people where they already are

Best channels:

- `Zalo`
- `SMS`
- `Telegram`

Implementation:

- add subscriptions by zone and role
- send only high-signal alerts
- support quiet hours and escalation rules

## Buzzwords To Avoid For Now

These may sound impressive but do not strengthen the product enough right now:

- `blockchain`
- `agent swarm`
- `federated learning`
- `GNNs`
- `microservices-first Kafka redesign`

They add complexity without solving the clearest product gaps.

## Target Architecture

### Existing Core

- FastAPI API
- PostgreSQL storage
- Celery jobs
- websocket updates
- React operator dashboard
- anomaly scoring and alert generation

### Recommended Additions

- `PostGIS`: geospatial storage and downstream mapping
- `MapLibre`: community-facing risk map
- `LightGBM` or `XGBoost`: predictive risk layer
- `LLM summary service`: structured, guarded explanation output
- `Notification dispatcher`: SMS, Zalo, Telegram
- `Incident workflow`: acknowledge, assign, resolve, annotate

## Data Model Additions

Add these tables first:

- `community_zones`
  - id, name, district, province, geometry, population_estimate
- `community_assets`
  - id, zone_id, type, name, geometry, sensitivity
  - example types: school, clinic, intake, fish_farm
- `incident_records`
  - id, station_id, severity, status, started_at, resolved_at, summary, recommended_action
- `risk_forecasts`
  - id, station_id, zone_id, horizon_hours, risk_score, risk_level, generated_at
- `notification_subscriptions`
  - id, channel, zone_id, audience_type, destination, is_active

## API Additions

Keep the current operator endpoints. Add community-specific endpoints alongside them.

Recommended new endpoints:

- `GET /api/community/overview`
  - summary of current risk by district or zone
- `GET /api/community/zones`
  - geospatial features for the map
- `GET /api/community/feed`
  - public-safe incident feed with plain-language summaries
- `GET /api/community/risk-forecast`
  - near-term forecast by zone
- `POST /api/community/subscriptions`
  - subscribe a user or channel to alerts
- `POST /api/incidents/{id}/acknowledge`
- `POST /api/incidents/{id}/resolve`

## Frontend Changes

Split the product into routes instead of one mixed dashboard.

Recommended routes:

- `/ops`
  - current dashboard, ingest actions, device control, alert management
- `/community`
  - map, zone status cards, incident feed, plain-language updates
- `/community/:zoneId`
  - local view for one district or community zone

Recommended community screens:

- `Map View`
  - color-coded zone status
  - station markers
  - affected assets
- `What This Means`
  - human-readable explanation of the current risk
- `What To Do Next`
  - simple guidance by audience
- `Recent Updates`
  - time-ordered status feed

## Delivery Plan

### Phase 1: Make It Community-Readable

Goal:

- convert the existing dashboard into a two-view product

Scope:

- split `Operator Console` and `Community View`
- add plain-language risk levels
- add incident workflow states
- remove hardcoded local frontend config
- add basic tests for alert and device flows

Recommended stack additions:

- none required yet beyond route split

Success signal:

- a non-technical user can understand the current situation without reading raw metrics

### Phase 2: Add GeoAI

Goal:

- show who is affected, not just which station is abnormal

Scope:

- enable `PostGIS`
- add `community_zones` and `community_assets`
- build community map with `MapLibre`
- connect stations to nearby zones and assets

Recommended stack additions:

- `PostGIS`
- `MapLibre`

Success signal:

- the system can answer `which nearby communities, schools, or farms may be affected`

### Phase 3: Add Predictive Risk

Goal:

- move from detection to early warning

Scope:

- add forecasting jobs
- train station-specific risk models
- generate 6-hour, 12-hour, and 24-hour risk levels
- expose risk forecasts in community and operator views

Recommended stack additions:

- `LightGBM` or `XGBoost`

Success signal:

- operators get warning before incident escalation, not only after a threshold breach

### Phase 4: Add LLM Explanations and Notifications

Goal:

- make alerts understandable and actionable at community scale

Scope:

- generate plain-language explanations in Vietnamese
- tailor recommendations by audience
- dispatch important alerts to subscribed channels

Recommended stack additions:

- guarded LLM service
- Zalo, SMS, or Telegram integrations

Success signal:

- community updates are short, clear, and can be pushed beyond the dashboard

## Recommended Immediate Build Order

If engineering time is limited, implement in this order:

1. split the frontend into `ops` and `community`
2. add incident status and human-readable risk categories
3. move to environment-based frontend config
4. add `PostGIS` and a basic map page
5. add zone and asset tables
6. add a forecast job with station-specific baselines
7. add LLM summaries for operator and community outputs
8. add notification subscriptions

## Product Framing

The strongest framing for this roadmap is:

`AnomalyGuard is an early-warning and response platform that helps local operators detect water risk before nearby communities, schools, and fish-farm households pay the price.`

That framing is more focused, more defensible, and much closer to the real value of the system than a generic `AI anomaly dashboard`.
