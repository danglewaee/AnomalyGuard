import { communityRiskMeta } from "../lib/risk.js";

const MAP_WIDTH = 760;
const MAP_HEIGHT = 420;
const MAP_PADDING = 52;

function compactZoneName(value) {
  if (value.length <= 22) return value;
  return `${value.slice(0, 19)}...`;
}

function normalizePoint(value, min, max, start, end) {
  if (min === max) return (start + end) / 2;
  const ratio = (value - min) / (max - min);
  return start + ratio * (end - start);
}

function projectZone(zone, bounds) {
  const x = normalizePoint(zone.centroid_longitude, bounds.minLng, bounds.maxLng, MAP_PADDING, MAP_WIDTH - MAP_PADDING);
  const y = normalizePoint(zone.centroid_latitude, bounds.maxLat, bounds.minLat, MAP_PADDING, MAP_HEIGHT - MAP_PADDING);
  return { x, y };
}

function CommunityMap({ zones, selectedZoneId, onSelectZone }) {
  const mappableZones = zones.filter(
    (zone) => typeof zone.centroid_latitude === "number" && typeof zone.centroid_longitude === "number"
  );

  if (mappableZones.length === 0) {
    return (
      <div className="communityMapShell empty">
        <p className="muted">Map view will appear once monitored zones have location data.</p>
      </div>
    );
  }

  const latitudes = mappableZones.map((zone) => zone.centroid_latitude);
  const longitudes = mappableZones.map((zone) => zone.centroid_longitude);
  const bounds = {
    minLat: Math.min(...latitudes),
    maxLat: Math.max(...latitudes),
    minLng: Math.min(...longitudes),
    maxLng: Math.max(...longitudes),
  };

  const ribbonPoints = [...mappableZones]
    .sort((left, right) => right.centroid_latitude - left.centroid_latitude || left.centroid_longitude - right.centroid_longitude)
    .map((zone) => {
      const point = projectZone(zone, bounds);
      return `${point.x},${point.y}`;
    })
    .join(" ");

  return (
    <div className="communityMapShell">
      <div className="mapCanvas">
        <svg className="communityMap" viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label="Community water risk map">
          <defs>
            <linearGradient id="map-surface-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#f7fbff" />
              <stop offset="100%" stopColor="#e8f1fb" />
            </linearGradient>
            <linearGradient id="river-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#8bc2ff" />
              <stop offset="100%" stopColor="#2d86d8" />
            </linearGradient>
          </defs>
          <rect className="mapBackdrop" x="0" y="0" width={MAP_WIDTH} height={MAP_HEIGHT} rx="26" fill="url(#map-surface-gradient)" />
          <path
            d={`M ${MAP_PADDING - 8} ${MAP_PADDING + 24} C ${MAP_WIDTH * 0.3} ${MAP_HEIGHT * 0.18}, ${MAP_WIDTH * 0.42} ${
              MAP_HEIGHT * 0.78
            }, ${MAP_WIDTH - MAP_PADDING + 8} ${MAP_HEIGHT - MAP_PADDING - 18}`}
            className="mapRiverShadow"
          />
          <path
            d={`M ${MAP_PADDING - 12} ${MAP_PADDING + 20} C ${MAP_WIDTH * 0.3} ${MAP_HEIGHT * 0.16}, ${MAP_WIDTH * 0.42} ${
              MAP_HEIGHT * 0.76
            }, ${MAP_WIDTH - MAP_PADDING + 10} ${MAP_HEIGHT - MAP_PADDING - 22}`}
            className="mapRiver"
          />
          {ribbonPoints ? <polyline className="mapConnector" points={ribbonPoints} /> : null}
          {mappableZones.map((zone) => {
            const meta = communityRiskMeta(zone.risk_level);
            const point = projectZone(zone, bounds);
            const isSelected = zone.zone_id === selectedZoneId;

            return (
              <g
                key={zone.zone_id}
                className={`mapMarker ${meta.className} ${isSelected ? "selected" : ""}`}
                onClick={() => onSelectZone(zone.zone_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectZone(zone.zone_id);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <circle className="mapMarkerHalo" cx={point.x} cy={point.y} r={isSelected ? 30 : 22} />
                <circle className="mapMarkerDot" cx={point.x} cy={point.y} r={isSelected ? 11 : 9} />
                <text className="mapLabel" x={point.x + 16} y={point.y - 6}>
                  {compactZoneName(zone.name)}
                </text>
                <text className="mapSubLabel" x={point.x + 16} y={point.y + 14}>
                  {zone.recent_alert_count} alerts / {zone.station_count} stations
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mapLegend">
        {["stable", "watch", "warning", "critical"].map((level) => {
          const meta = communityRiskMeta(level);
          return (
            <div key={level} className={`legendItem ${meta.className}`}>
              <span className="legendDot" />
              <strong>{meta.label}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default CommunityMap;
