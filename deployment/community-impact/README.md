## Community Impact Profiles

These JSON files are deployment data, not product logic.

Use them to customize:

- corridor wording for community updates
- audience groups that should hear a warning first
- priority sites to mention in public-safe messaging
- signal-specific impact rules for turbidity, oxygen, pH, TDS, or other factors

Default file:

- `deployment/community-impact/default.json`

Sample profiles:

- `deployment/community-impact/urban-river.json`
- `deployment/community-impact/aquaculture-delta.json`
- `deployment/community-impact/rural-drinking-water.json`

Override with env:

- `COMMUNITY_IMPACT_PROFILE_PATH`

Recommended workflow:

1. copy `default.json`
2. adjust audience labels and priority sites for your deployment
3. point `COMMUNITY_IMPACT_PROFILE_PATH` to that file

Quick starting point:

- use `urban-river.json` for city waterway deployments with clinics, schools, refill points, and treatment-heavy infrastructure
- use `aquaculture-delta.json` for canal and pond-heavy deployments where intake timing and oxygen stress matter operationally
- use `rural-drinking-water.json` for shared tanks, simple filtration, and small public-service sites that depend on direct intake or low-complexity treatment

Keep this layer generic and deployment-focused. Do not put province-specific logic into backend code paths.
