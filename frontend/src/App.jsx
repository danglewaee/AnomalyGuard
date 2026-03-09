import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/stream";

const VN_STATIONS = [
  { id: "mekong-can-tho", label: "Can Tho (Mekong)" },
  { id: "saigon-thu-duc", label: "Thu Duc (Saigon River)" },
  { id: "red-river-ha-noi", label: "Long Bien (Red River)" },
];

function App() {
  const [readings, setReadings] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stations, setStations] = useState([]);
  const [meta, setMeta] = useState(null);
  const [connected, setConnected] = useState(false);
  const [stationId, setStationId] = useState("all");
  const [sinceMinutes, setSinceMinutes] = useState(180);
  const [vnIngestStation, setVnIngestStation] = useState("mekong-can-tho");
  const [ingestMessage, setIngestMessage] = useState("");
  const [ingesting, setIngesting] = useState(false);

  const loadSnapshot = useCallback((selectedStation, selectedWindow) => {
    const stationParam = selectedStation === "all" ? "" : `&station_id=${selectedStation}`;

    fetch(`${API_BASE}/api/stations`)
      .then((res) => res.json())
      .then((data) => setStations(data))
      .catch(() => {});

    fetch(`${API_BASE}/api/meta`)
      .then((res) => res.json())
      .then((data) => setMeta(data))
      .catch(() => {});

    fetch(`${API_BASE}/api/readings/latest?limit=400&since_minutes=${selectedWindow}${stationParam}`)
      .then((res) => res.json())
      .then((data) => setReadings(data))
      .catch(() => {});

    fetch(`${API_BASE}/api/alerts/latest?limit=150&since_minutes=${selectedWindow}${stationParam}`)
      .then((res) => res.json())
      .then((data) => setAlerts(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadSnapshot(stationId, sinceMinutes);

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.event === "bootstrap") {
        setStations(data.payload.stations || []);
        setMeta(data.payload.meta || null);
        setReadings(data.payload.readings || []);
        setAlerts(data.payload.alerts || []);
      }

      if (data.event === "station_registered") {
        setIngestMessage(
          `Ingested ${data.payload.inserted_readings} readings from ${data.payload.station.station_name}`
        );
        loadSnapshot(stationId, sinceMinutes);
      }

      if (data.event === "reading") {
        setReadings((prev) => [...prev.slice(-399), data.payload]);
      }

      if (data.event === "alert") {
        setAlerts((prev) => [data.payload, ...prev].slice(0, 150));
      }
    };

    const heartbeat = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 10000);

    return () => {
      clearInterval(heartbeat);
      ws.close();
    };
  }, [loadSnapshot]);

  useEffect(() => {
    loadSnapshot(stationId, sinceMinutes);
  }, [stationId, sinceMinutes, loadSnapshot]);

  const runVNIngest = async () => {
    setIngestMessage("");
    setIngesting(true);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/vn?station_id=${vnIngestStation}&days=30`, {
        method: "POST",
      });
      const body = await res.json();
      if (!res.ok) {
        setIngestMessage(body.detail || "VN ingest failed");
      } else {
        setIngestMessage(
          `VN ingest success: ${body.inserted_readings} readings, ${body.generated_alerts} alerts (${body.station.station_id})`
        );
        setStationId(body.station.station_id);
        loadSnapshot(body.station.station_id, sinceMinutes);
      }
    } catch {
      setIngestMessage("Cannot reach backend or Open-Meteo endpoint.");
    } finally {
      setIngesting(false);
    }
  };

  const filteredReadings = useMemo(() => {
    if (stationId === "all") return readings;
    return readings.filter((r) => r.station_id === stationId);
  }, [readings, stationId]);

  const filteredAlerts = useMemo(() => {
    if (stationId === "all") return alerts;
    return alerts.filter((a) => a.station_id === stationId);
  }, [alerts, stationId]);

  const latest = filteredReadings[filteredReadings.length - 1];

  const chartData = useMemo(
    () =>
      filteredReadings.map((r) => ({
        t: new Date(r.timestamp).toLocaleTimeString(),
        turbidity: r.turbidity,
        tds: r.tds,
        ph: r.ph,
      })),
    [filteredReadings]
  );

  return (
    <div className="layout">
      <header className="header">
        <h1>AnomalyGuard - Water Pollution MVP</h1>
        <span className={connected ? "badge ok" : "badge err"}>
          {connected ? "Realtime Connected" : "Disconnected"}
        </span>
      </header>

      <section className="panel controls">
        <div>
          <label htmlFor="station">Station</label>
          <select id="station" value={stationId} onChange={(e) => setStationId(e.target.value)}>
            <option value="all">All Stations</option>
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.station_name} ({s.region})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="window">Time Window</label>
          <select id="window" value={sinceMinutes} onChange={(e) => setSinceMinutes(Number(e.target.value))}>
            <option value={60}>Last 60 minutes</option>
            <option value={180}>Last 3 hours</option>
            <option value={720}>Last 12 hours</option>
            <option value={1440}>Last 24 hours</option>
            <option value={4320}>Last 3 days</option>
            <option value={10080}>Last 7 days</option>
          </select>
        </div>
        <div className="metaBlock">
          <strong>Data Source:</strong> {meta?.data_source || "-"}
          <br />
          <strong>Time Context:</strong> {meta?.timezone || "-"}
          <br />
          <strong>Note:</strong> {meta?.last_ingest_note || "-"}
        </div>
      </section>

      <section className="panel ingestPanel">
        <div>
          <label htmlFor="vnStation">VN Station (Real Feed)</label>
          <select id="vnStation" value={vnIngestStation} onChange={(e) => setVnIngestStation(e.target.value)}>
            {VN_STATIONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <button onClick={runVNIngest} disabled={ingesting}>
          {ingesting ? "Ingesting..." : "Ingest VN Real Data"}
        </button>
        <div className="muted tiny">
          {ingestMessage || "Uses Open-Meteo flood/weather data at VN coordinates for the last 30 days."}
        </div>
      </section>

      <section className="cards">
        <Metric title="pH" value={latest ? latest.ph : "-"} />
        <Metric title="TDS" value={latest ? `${latest.tds} ppm` : "-"} />
        <Metric title="Turbidity" value={latest ? `${latest.turbidity} NTU` : "-"} />
        <Metric title="DO" value={latest ? `${latest.do_mg_l} mg/L` : "-"} />
      </section>

      <section className="grid">
        <div className="panel">
          <h2>Water Signals</h2>
          <div className="chartWrap">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="t" hide />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="turbidity" stroke="#d64545" dot={false} />
                <Line type="monotone" dataKey="tds" stroke="#1d6fd4" dot={false} />
                <Line type="monotone" dataKey="ph" stroke="#24937e" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <h2>Recent Alerts</h2>
          <div className="alerts">
            {filteredAlerts.length === 0 && <p className="muted">No anomalies in selected scope.</p>}
            {filteredAlerts.map((a) => (
              <div key={a.id} className={`alertItem sev-${a.severity}`}>
                <div className="alertHead">
                  <strong>{a.severity.toUpperCase()}</strong>
                  <span>score: {a.score}</span>
                </div>
                <div className="alertReasons">{(a.reasons || []).join(", ") || "anomalous pattern"}</div>
                <div className="muted tiny">
                  {new Date(a.timestamp).toLocaleString()} - {a.station_id}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({ title, value }) {
  return (
    <div className="card">
      <p>{title}</p>
      <strong>{value}</strong>
    </div>
  );
}

export default App;
