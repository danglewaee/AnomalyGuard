# Community View Implementation Notes

This file maps the roadmap to the current codebase so implementation can start without re-discovery.

## Current Strengths In The Repo

- realtime websocket bootstrap already carries stations, readings, alerts, and device statuses
- device telemetry and device control are already modeled
- metadata endpoint already exposes source and counts
- alert explain endpoint already exists for protected views

Useful files:

- `backend/app/main.py`
- `backend/app/services/detector.py`
- `backend/app/services/store_pg.py`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`

## High-Leverage Refactors

### Frontend

Break `frontend/src/App.jsx` into:

- `src/routes/OpsView.jsx`
- `src/routes/CommunityView.jsx`
- `src/components/AlertFeed.jsx`
- `src/components/RiskBadge.jsx`
- `src/components/CommunityMap.jsx`
- `src/components/IncidentTimeline.jsx`

This will reduce coupling between operator-only controls and public-safe messaging.

### Backend

Split API domains:

- `app/api/ops.py`
- `app/api/community.py`
- `app/api/device.py`
- `app/api/incidents.py`

This will make it easier to apply different auth and response shapes for public-safe data.

### Detector

Keep the current detector for baseline anomaly detection, but add a separate forecast pipeline instead of mixing prediction logic into the realtime path.

Recommended separation:

- `detector.py`
  - realtime anomaly detection
- `forecasting.py`
  - scheduled risk forecasts
- `explanations.py`
  - structured explanation payloads for UI and LLM summary generation

## First Community View Payload Shape

Suggested `GET /api/community/overview` response:

```json
{
  "generated_at": "2026-03-22T14:00:00Z",
  "zones": [
    {
      "zone_id": "river-zone-01",
      "name": "River Zone 01",
      "risk_level": "medium",
      "headline": "Water quality signals are unstable near monitored points.",
      "recommended_action": "Avoid using untreated water directly until the next update.",
      "affected_assets": [
        { "type": "school", "count": 2 },
        { "type": "intake", "count": 3 }
      ]
    }
  ]
}
```

This keeps the community contract small and stable.

Deployment-specific audience labels or corridor wording should come from a configurable impact profile, not from hardcoded province logic in the payload schema.

Default repo location for that profile:

- `deployment/community-impact/default.json`

## First Incident Model

Suggested status enum:

- `open`
- `acknowledged`
- `monitoring`
- `resolved`
- `false_positive`

Suggested severity enum:

- `low`
- `medium`
- `high`
- `critical`

## Guardrails For LLM Use

Only send structured fields such as:

- risk level
- top contributing factors
- recent trend direction
- affected zone
- approved recommendation templates

Do not send the whole database or raw operator notes into the prompt.

## Phase 1 Definition Of Done

- operator controls no longer appear in the community route
- community route can render a safe summary from current alerts
- alert cards include human-readable consequences
- incident states are stored and shown in ops view
- frontend config uses environment variables instead of hardcoded localhost values
- tests cover alert serialization and community overview responses
