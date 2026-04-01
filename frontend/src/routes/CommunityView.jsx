import { useEffect, useMemo, useState } from "react";

import CommunityMap from "../components/CommunityMap.jsx";
import RiskPill from "../components/RiskPill.jsx";
import { COMMUNITY_WINDOW_OPTIONS } from "../constants.js";
import { communityRiskMeta, formatTimestamp } from "../lib/risk.js";

function CommunityView({
  communityOverview,
  communityImpactProfiles,
  communityImpactProfile,
  communitySinceMinutes,
  onCommunityImpactProfileChange,
  onCommunityWindowChange,
}) {
  const zones = communityOverview?.zones || [];
  const summary = communityOverview?.summary;
  const urgentZones = zones.filter((zone) => zone.risk_level === "warning" || zone.risk_level === "critical");
  const [selectedZoneId, setSelectedZoneId] = useState("");
  const selectedImpactProfile =
    communityImpactProfiles.find((profile) => profile.key === (communityImpactProfile || communityOverview?.impact_profile)) || null;

  const defaultZoneId = useMemo(() => urgentZones[0]?.zone_id || zones[0]?.zone_id || "", [urgentZones, zones]);

  useEffect(() => {
    if (!defaultZoneId) {
      setSelectedZoneId("");
      return;
    }

    if (!selectedZoneId || !zones.some((zone) => zone.zone_id === selectedZoneId)) {
      setSelectedZoneId(defaultZoneId);
    }
  }, [defaultZoneId, selectedZoneId, zones]);

  const selectedZone = zones.find((zone) => zone.zone_id === selectedZoneId) || null;

  return (
    <div className="page">
      <section className="pageIntro communityIntro">
        <div>
          <p className="eyebrow">Community View</p>
          <h1>Water updates people can understand and act on</h1>
          <p className="lede">
            This view translates monitoring data into location-based risk updates for households, schools, farms, and local
            administrators. It is intentionally public-safe and non-operational.
          </p>
        </div>
        <div className="heroCard">
          <span className="statusLabel">Current Headline</span>
          <strong>{communityOverview?.headline || "Waiting for monitored data."}</strong>
          <p className="muted tiny">
            Impact profile: {selectedImpactProfile?.display_name || communityOverview?.impact_profile_name || "Environment default"}
          </p>
          <p className="muted">
            {communityOverview?.generated_at ? `Updated ${formatTimestamp(communityOverview.generated_at)}` : "No community update yet"}
          </p>
        </div>
      </section>

      <section className="panel communityToolbar">
        <div>
          <label htmlFor="communityWindow">Monitoring Window</label>
          <select id="communityWindow" value={communitySinceMinutes} onChange={(event) => onCommunityWindowChange(Number(event.target.value))}>
            {COMMUNITY_WINDOW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="communityProfile">Impact Profile</label>
          <select id="communityProfile" value={communityImpactProfile} onChange={(event) => onCommunityImpactProfileChange(event.target.value)}>
            {communityImpactProfiles.length === 0 ? <option value="">Environment default</option> : null}
            {communityImpactProfiles.map((profile) => (
              <option key={profile.key} value={profile.key}>
                {profile.display_name}
              </option>
            ))}
          </select>
          <div className="muted tiny profileHelp">
            {selectedImpactProfile?.description || "Choose how community-facing impact copy should be framed for this demo."}
          </div>
        </div>
        <div className="communitySummaryGrid">
          <SummaryCard title="Monitored Zones" value={summary?.monitored_zones ?? 0} />
          <SummaryCard title="Zones At Risk" value={summary?.zones_at_risk ?? 0} />
          <SummaryCard title="Recent Alerts" value={summary?.recent_alerts ?? 0} />
        </div>
      </section>

      <section className="signalBand">
        <SignalBandItem label="Stable" value={summary?.stable ?? 0} level="stable" />
        <SignalBandItem label="Watch" value={summary?.watch ?? 0} level="watch" />
        <SignalBandItem label="Warning" value={summary?.warning ?? 0} level="warning" />
        <SignalBandItem label="Critical" value={summary?.critical ?? 0} level="critical" />
      </section>

      <section className="communityGrid">
        <div className="panel">
          <div className="sectionTitle">
            <h2>Map Coverage</h2>
            <p className="muted">A public-safe geographic layer that can later move to PostGIS and MapLibre.</p>
          </div>
          <CommunityMap zones={zones} selectedZoneId={selectedZoneId} onSelectZone={setSelectedZoneId} />
          {selectedZone ? (
            <div className={`mapFocus mapFocus-${selectedZone.risk_level}`}>
              <div className="zoneHead">
                <div>
                  <p className="eyebrow">Selected Zone</p>
                  <h3>{selectedZone.name}</h3>
                </div>
                <RiskPill level={selectedZone.risk_level} />
              </div>
              <p className="zoneHeadline">{selectedZone.headline}</p>
              <p className="zoneMessage">{selectedZone.community_message}</p>
              <div className="chipRow">
                <span className="signalChip secondary">{selectedZone.station_count} stations</span>
                {selectedZone.top_signals.map((signal) => (
                  <span key={signal} className="signalChip">
                    {signal}
                  </span>
                ))}
              </div>
              <div className="impactBox">
                <strong>Downstream Impact</strong>
                <p className="impactStatement">{selectedZone.impact_statement}</p>
                <div className="muted tiny">Corridor: {selectedZone.downstream_corridor}</div>
              </div>
              <div className="impactGrid">
                <div className="impactCard">
                  <span className="statusLabel">Who Needs This First</span>
                  <div className="chipRow">
                    {selectedZone.impacted_groups.map((group) => (
                      <span key={group} className="signalChip">
                        {group}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="impactCard">
                  <span className="statusLabel">Priority Sites</span>
                  <div className="chipRow">
                    {selectedZone.priority_sites.map((site) => (
                      <span key={site} className="signalChip secondary">
                        {site}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="mapStationGrid">
                {selectedZone.stations.map((station) => (
                  <div key={station.station_id} className="mapStationItem">
                    <strong>{station.station_name}</strong>
                    <span>{station.station_id}</span>
                    <span>
                      {station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
                    </span>
                  </div>
                ))}
              </div>
              <div className="muted tiny">Latest update: {formatTimestamp(selectedZone.latest_update_at)}</div>
            </div>
          ) : null}

          <div className="sectionTitle areaStatusHeader">
            <h2>Area Status</h2>
            <p className="muted">Grouped by monitored region so public updates stay readable.</p>
          </div>
          <div className="zoneGrid">
            {zones.length === 0 && <p className="muted">No community summary is available yet.</p>}
            {zones.map((zone) => {
              const meta = communityRiskMeta(zone.risk_level);
              return (
                <article
                  key={zone.zone_id}
                  className={`zoneCard zone-${meta.className} ${selectedZoneId === zone.zone_id ? "isSelected" : ""}`}
                  onClick={() => setSelectedZoneId(zone.zone_id)}
                >
                  <div className="zoneHead">
                    <RiskPill level={zone.risk_level} />
                    <span className="tiny muted">{zone.recent_alert_count} recent alerts</span>
                  </div>
                  <h3>{zone.name}</h3>
                  <p className="zoneHeadline">{zone.headline}</p>
                  <p className="zoneMessage">{zone.community_message}</p>
                  <div className="zoneActionBox">
                    <strong>What To Do Next</strong>
                    <p>{zone.recommended_action}</p>
                  </div>
                  <div className="impactSnippet">
                    <strong>Downstream impact</strong>
                    <p>{zone.impact_statement}</p>
                  </div>
                  <div className="chipRow">
                    {zone.top_signals.map((signal) => (
                      <span key={signal} className="signalChip">
                        {signal}
                      </span>
                    ))}
                    {zone.station_names.slice(0, 2).map((name) => (
                      <span key={name} className="signalChip secondary">
                        {name}
                      </span>
                    ))}
                  </div>
                  <div className="muted tiny">Latest update: {formatTimestamp(zone.latest_update_at)}</div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="communitySide">
          <section className="panel">
            <div className="sectionTitle">
              <h2>Who Needs This First</h2>
              <p className="muted">Use the selected zone to guide the first public-safe update.</p>
            </div>
            {selectedZone ? (
              <div className="storyGrid">
                <StoryCard title="Impact Summary" body={selectedZone.impact_statement} />
                <StoryCard title="Downstream Corridor" body={selectedZone.downstream_corridor} />
              </div>
            ) : (
              <p className="muted">Select a zone to view downstream priorities.</p>
            )}
            {selectedZone ? (
              <div className="impactGrid sideImpactGrid">
                <div className="impactCard">
                  <span className="statusLabel">First Audiences</span>
                  <div className="chipRow">
                    {selectedZone.impacted_groups.map((group) => (
                      <span key={group} className="signalChip">
                        {group}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="impactCard">
                  <span className="statusLabel">Priority Sites</span>
                  <div className="chipRow">
                    {selectedZone.priority_sites.map((site) => (
                      <span key={site} className="signalChip secondary">
                        {site}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          <section className="panel">
            <div className="sectionTitle">
              <h2>Priority Feed</h2>
              <p className="muted">Areas that should be reviewed first before publishing updates.</p>
            </div>
            <div className="priorityFeed">
              {urgentZones.length === 0 && <p className="muted">No warning or critical zones in this monitoring window.</p>}
              {urgentZones.map((zone) => (
                <div
                  key={zone.zone_id}
                  className={`priorityItem ${selectedZoneId === zone.zone_id ? "isSelected" : ""}`}
                  onClick={() => setSelectedZoneId(zone.zone_id)}
                >
                  <div className="zoneHead">
                    <RiskPill level={zone.risk_level} />
                    <strong>{zone.name}</strong>
                  </div>
                  <p>{zone.recommended_action}</p>
                  <div className="muted tiny">Notify first: {zone.impacted_groups.slice(0, 2).join(", ") || "Downstream communities"}</div>
                  <div className="muted tiny">{formatTimestamp(zone.latest_update_at)}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

function SummaryCard({ title, value }) {
  return (
    <div className="summaryCard">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SignalBandItem({ label, value, level }) {
  const meta = communityRiskMeta(level);
  return (
    <div className={`signalBandItem ${meta.className}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StoryCard({ title, body }) {
  return (
    <article className="storyCard">
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
  );
}

export default CommunityView;
