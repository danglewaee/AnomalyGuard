import { useCallback, useEffect, useMemo, useState } from "react";

import { API_BASE, WS_URL } from "./config.js";
import { EMPTY_DEVICE_CONTROL } from "./constants.js";
import CommunityView from "./routes/CommunityView.jsx";
import OpsView from "./routes/OpsView.jsx";

const OPS_PATH = "/ops";
const COMMUNITY_PATH = "/community";

function currentPathname() {
  if (typeof window === "undefined") return OPS_PATH;
  return window.location.pathname || OPS_PATH;
}

function normalizeRoute(pathname) {
  return pathname.startsWith(COMMUNITY_PATH) ? COMMUNITY_PATH : OPS_PATH;
}

function App() {
  const [route, setRoute] = useState(() => normalizeRoute(currentPathname()));

  const [readings, setReadings] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stations, setStations] = useState([]);
  const [deviceStatuses, setDeviceStatuses] = useState([]);
  const [meta, setMeta] = useState(null);
  const [communityOverview, setCommunityOverview] = useState(null);
  const [communityImpactProfiles, setCommunityImpactProfiles] = useState([]);
  const [communityImpactProfile, setCommunityImpactProfile] = useState("");
  const [connected, setConnected] = useState(false);

  const [stationId, setStationId] = useState("all");
  const [sinceMinutes, setSinceMinutes] = useState(180);
  const [communitySinceMinutes, setCommunitySinceMinutes] = useState(720);
  const [vnIngestStation, setVnIngestStation] = useState("mekong-can-tho");
  const [ingestMessage, setIngestMessage] = useState("");
  const [ingesting, setIngesting] = useState(false);

  const [authToken, setAuthToken] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [authMessage, setAuthMessage] = useState("");

  const [deviceStationId, setDeviceStationId] = useState("");
  const [deviceControl, setDeviceControl] = useState(EMPTY_DEVICE_CONTROL);
  const [deviceMessage, setDeviceMessage] = useState("");
  const [controlBusy, setControlBusy] = useState(false);
  const [controlDirty, setControlDirty] = useState(false);
  const [incidentBusyId, setIncidentBusyId] = useState("");
  const [incidentMessage, setIncidentMessage] = useState("");
  const [reviewExportBusy, setReviewExportBusy] = useState(false);
  const [reviewExportMessage, setReviewExportMessage] = useState("");
  const [alertActionNotes, setAlertActionNotes] = useState({});
  const [alertHistoryById, setAlertHistoryById] = useState({});
  const [expandedHistoryAlertId, setExpandedHistoryAlertId] = useState("");
  const [historyBusyId, setHistoryBusyId] = useState("");
  const [reviewReadiness, setReviewReadiness] = useState(null);
  const [reviewEvaluation, setReviewEvaluation] = useState(null);
  const [reviewInsightsBusy, setReviewInsightsBusy] = useState(false);
  const [reviewInsightsMessage, setReviewInsightsMessage] = useState("Login admin to inspect reviewed dataset quality.");
  const [retrainingJobBusy, setRetrainingJobBusy] = useState(false);
  const [retrainingJobMessage, setRetrainingJobMessage] = useState("");
  const [lastRetrainingBundle, setLastRetrainingBundle] = useState(null);

  const navigate = useCallback((nextRoute) => {
    const normalized = normalizeRoute(nextRoute);
    if (typeof window !== "undefined" && currentPathname() !== normalized) {
      window.history.pushState({}, "", normalized);
    }
    setRoute(normalized);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    if (window.location.pathname === "/" || window.location.pathname === "") {
      window.history.replaceState({}, "", OPS_PATH);
      setRoute(OPS_PATH);
    }

    const onPopState = () => setRoute(normalizeRoute(currentPathname()));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const upsertDeviceStatus = useCallback((incoming) => {
    setDeviceStatuses((previous) => {
      const next = [incoming, ...previous.filter((item) => item.station_id !== incoming.station_id)];
      next.sort((left, right) => {
        const leftTime = left.last_seen_at ? new Date(left.last_seen_at).getTime() : 0;
        const rightTime = right.last_seen_at ? new Date(right.last_seen_at).getTime() : 0;
        return rightTime - leftTime;
      });
      return next;
    });
  }, []);

  const upsertAlert = useCallback((incoming) => {
    setAlerts((previous) => {
      const next = [incoming, ...previous.filter((item) => item.id !== incoming.id)];
      next.sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());
      return next.slice(0, 150);
    });
  }, []);

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

    fetch(`${API_BASE}/api/device/status`)
      .then((res) => res.json())
      .then((data) => setDeviceStatuses(data))
      .catch(() => {});
  }, []);

  const loadCommunityProfiles = useCallback(() => {
    fetch(`${API_BASE}/api/community/impact-profiles`)
      .then((res) => res.json())
      .then((data) => {
        const profiles = data.profiles || [];
        setCommunityImpactProfiles(profiles);
        setCommunityImpactProfile((previous) => {
          if (previous && profiles.some((item) => item.key === previous)) {
            return previous;
          }
          return data.active_profile || profiles[0]?.key || "";
        });
      })
      .catch(() => {});
  }, []);

  const loadCommunityOverview = useCallback((selectedWindow, selectedProfile = "") => {
    const params = new URLSearchParams({ since_minutes: String(selectedWindow) });
    if (selectedProfile) {
      params.set("impact_profile", selectedProfile);
    }

    fetch(`${API_BASE}/api/community/overview?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => setCommunityOverview(data))
      .catch(() => {});
  }, []);

  const loadReviewInsights = useCallback(
    async (selectedStation = stationId, selectedWindow = sinceMinutes, options = {}) => {
      const { suppressErrors = false, silentSuccess = true } = options;
      if (!authToken) {
        setReviewReadiness(null);
        setReviewEvaluation(null);
        setReviewInsightsMessage("Login admin to inspect reviewed dataset quality.");
        return;
      }

      const baseParams = new URLSearchParams({
        since_minutes: String(selectedWindow),
        limit: "1000",
      });
      if (selectedStation !== "all") {
        baseParams.set("station_id", selectedStation);
      }
      const readinessParams = new URLSearchParams(baseParams);
      readinessParams.set("recent_count", "50");

      setReviewInsightsBusy(true);
      try {
        const headers = { Authorization: `Bearer ${authToken}` };
        const [readinessRes, evaluationRes] = await Promise.all([
          fetch(`${API_BASE}/api/alerts/labeled/readiness?${readinessParams.toString()}`, { headers }),
          fetch(`${API_BASE}/api/alerts/labeled/evaluation?${baseParams.toString()}`, { headers }),
        ]);

        const readinessBody = await readinessRes.json();
        const evaluationBody = await evaluationRes.json();

        if (!readinessRes.ok) {
          if (!suppressErrors) {
            setReviewInsightsMessage(readinessBody.detail || "Reviewed dataset readiness failed to load.");
          }
          return;
        }
        if (!evaluationRes.ok) {
          if (!suppressErrors) {
            setReviewInsightsMessage(evaluationBody.detail || "Reviewed dataset evaluation failed to load.");
          }
          return;
        }

        setReviewReadiness(readinessBody);
        setReviewEvaluation(evaluationBody);
        if (!silentSuccess) {
          setReviewInsightsMessage("Reviewed dataset health refreshed.");
        }
      } catch {
        if (!suppressErrors) {
          setReviewInsightsMessage("Cannot reach backend for reviewed dataset health.");
        }
      } finally {
        setReviewInsightsBusy(false);
      }
    },
    [authToken, sinceMinutes, stationId]
  );

  useEffect(() => {
    loadSnapshot(stationId, sinceMinutes);
  }, [loadSnapshot, sinceMinutes, stationId]);

  useEffect(() => {
    loadCommunityProfiles();
  }, [loadCommunityProfiles]);

  useEffect(() => {
    loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
  }, [communityImpactProfile, communitySinceMinutes, loadCommunityOverview]);

  useEffect(() => {
    if (!authToken) {
      setReviewReadiness(null);
      setReviewEvaluation(null);
      setReviewInsightsMessage("Login admin to inspect reviewed dataset quality.");
      return;
    }
    loadReviewInsights(stationId, sinceMinutes, { suppressErrors: true, silentSuccess: true });
  }, [authToken, loadReviewInsights, sinceMinutes, stationId]);

  useEffect(() => {
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
        setDeviceStatuses(data.payload.device_statuses || []);
        loadCommunityProfiles();
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "station_registered") {
        setIngestMessage(`Ingested ${data.payload.inserted_readings} readings from ${data.payload.station.station_name}`);
        loadSnapshot(stationId, sinceMinutes);
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "stations_updated") {
        setStations(data.payload.stations || []);
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "reading") {
        setReadings((previous) => [...previous.slice(-399), data.payload]);
      }

      if (data.event === "alert") {
        upsertAlert(data.payload);
        setIncidentMessage("");
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "incident_status") {
        upsertAlert(data.payload);
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "alert_review") {
        upsertAlert(data.payload);
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
        if (authToken) {
          loadReviewInsights(stationId, sinceMinutes, { suppressErrors: true, silentSuccess: true });
        }
      }

      if (data.event === "device_status") {
        upsertDeviceStatus(data.payload);
        loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      }

      if (data.event === "device_control") {
        upsertDeviceStatus(data.payload);
        if (data.payload.station_id === deviceStationId) {
          setDeviceControl({ ...EMPTY_DEVICE_CONTROL, ...data.payload.control });
          setControlDirty(false);
          setDeviceMessage(`Control pushed to ${data.payload.station_name}`);
        }
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
  }, [
    communityImpactProfile,
    communitySinceMinutes,
    deviceStationId,
    loadCommunityOverview,
    loadCommunityProfiles,
    loadSnapshot,
    sinceMinutes,
    stationId,
    authToken,
    loadReviewInsights,
    upsertAlert,
    upsertDeviceStatus,
  ]);

  const deviceStations = useMemo(() => stations.filter((station) => station.source === "device"), [stations]);

  useEffect(() => {
    if (stationId !== "all") {
      const selected = stations.find((station) => station.station_id === stationId && station.source === "device");
      if (selected && selected.station_id !== deviceStationId) {
        setDeviceStationId(selected.station_id);
        setControlDirty(false);
        return;
      }
    }

    if (!deviceStationId && deviceStations.length > 0) {
      setDeviceStationId(deviceStations[0].station_id);
      setControlDirty(false);
      return;
    }

    if (deviceStationId && !deviceStations.some((station) => station.station_id === deviceStationId)) {
      setDeviceStationId(deviceStations[0]?.station_id || "");
      setControlDirty(false);
    }
  }, [deviceStationId, deviceStations, stationId, stations]);

  const selectedDeviceStatus = useMemo(
    () => deviceStatuses.find((item) => item.station_id === deviceStationId) || null,
    [deviceStatuses, deviceStationId]
  );

  useEffect(() => {
    if (!selectedDeviceStatus || controlDirty) return;
    setDeviceControl({ ...EMPTY_DEVICE_CONTROL, ...selectedDeviceStatus.control });
  }, [controlDirty, selectedDeviceStatus]);

  const runLogin = async () => {
    setAuthMessage("");
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);

    try {
      const res = await fetch(`${API_BASE}/api/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await res.json();
      if (!res.ok) {
        setAuthMessage(data.detail || "Login failed");
        return;
      }
      setAuthToken(data.access_token);
      setAuthMessage("Admin token ready");
      setReviewInsightsMessage("");
    } catch {
      setAuthMessage("Cannot reach backend");
    }
  };

  const runVNIngest = async () => {
    setIngestMessage("");
    if (!authToken) {
      setIngestMessage("Login admin first to run ingest.");
      return;
    }

    setIngesting(true);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/vn?station_id=${vnIngestStation}&days=30`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      const body = await res.json();
      if (!res.ok) {
        setIngestMessage(body.detail || "VN ingest failed");
      } else {
        const jobId = body.id;
        let jobFinished = false;
        setIngestMessage(`VN ingest job queued (${jobId}). Waiting for worker result...`);

        for (let attempt = 0; attempt < 60; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 2000));

          const jobRes = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
            headers: { Authorization: `Bearer ${authToken}` },
          });
          const jobBody = await jobRes.json();
          if (!jobRes.ok) {
            setIngestMessage(jobBody.detail || "Cannot read ingest job status.");
            break;
          }

          if (jobBody.status === "queued") {
            setIngestMessage(`VN ingest job queued (${jobId}).`);
            continue;
          }

          if (jobBody.status === "running") {
            setIngestMessage(`VN ingest job running (${jobId})...`);
            continue;
          }

          if (jobBody.status === "failed") {
            setIngestMessage(jobBody.error_message || "VN ingest job failed.");
            jobFinished = true;
            break;
          }

          if (jobBody.status === "succeeded") {
            const result = jobBody.result_payload || {};
            const station = result.station || null;
            if (station?.station_id) {
              setStationId(station.station_id);
              loadSnapshot(station.station_id, sinceMinutes);
            } else {
              loadSnapshot(stationId, sinceMinutes);
            }
            loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
            setIngestMessage(
              `VN ingest success: ${result.inserted_readings || 0} new readings, ${result.skipped_duplicates || 0} duplicates skipped, ${result.generated_alerts || 0} alerts${
                station?.station_id ? ` (${station.station_id})` : ""
              }`
            );
            jobFinished = true;
            break;
          }
        }

        if (!jobFinished) {
          setIngestMessage(`VN ingest job still running (${jobId}). Check again shortly.`);
        }
      }
    } catch {
      setIngestMessage("Cannot reach backend or Open-Meteo endpoint.");
    } finally {
      setIngesting(false);
    }
  };

  const updateDeviceControl = useCallback((patch) => {
    setControlDirty(true);
    setDeviceControl((previous) => ({ ...previous, ...patch }));
  }, []);

  const runDeviceControl = async () => {
    setDeviceMessage("");
    if (!authToken) {
      setDeviceMessage("Login admin first to push device control.");
      return;
    }
    if (!deviceStationId) {
      setDeviceMessage("No device station available yet.");
      return;
    }

    setControlBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/device/control/${deviceStationId}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(deviceControl),
      });
      const body = await res.json();
      if (!res.ok) {
        setDeviceMessage(body.detail || "Device control update failed");
      } else {
        setDeviceControl({ ...EMPTY_DEVICE_CONTROL, ...body.control });
        setControlDirty(false);
        setDeviceMessage(`Control updated for ${deviceStationId}`);
      }
    } catch {
      setDeviceMessage("Cannot reach backend for device control.");
    } finally {
      setControlBusy(false);
    }
  };

  const runIncidentAction = async (alertId, action) => {
    setIncidentMessage("");
    if (!authToken) {
      setIncidentMessage("Login admin first to update incident state.");
      return;
    }

    const note = (alertActionNotes[alertId] || "").trim();
    setIncidentBusyId(alertId);
    try {
      const res = await fetch(`${API_BASE}/api/incidents/${alertId}/${action}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ note }),
      });
      const body = await res.json();
      if (!res.ok) {
        setIncidentMessage(body.detail || "Incident update failed");
        return;
      }

      const actionCopy = {
        acknowledge: "acknowledged",
        resolve: "resolved",
        reopen: "reopened",
      };
      upsertAlert(body);
      loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      if (alertHistoryById[alertId] || expandedHistoryAlertId === alertId) {
        await loadAlertHistory(alertId, { force: true, suppressErrors: true });
      }
      await loadReviewInsights(stationId, sinceMinutes, { suppressErrors: true, silentSuccess: true });
      setAlertActionNotes((previous) => ({ ...previous, [alertId]: "" }));
      setIncidentMessage(
        `Incident ${actionCopy[action] || "updated"} for ${body.station_id}${note ? ". Note saved." : "."}`
      );
    } catch {
      setIncidentMessage("Cannot reach backend for incident update.");
    } finally {
      setIncidentBusyId("");
    }
  };

  const runAlertReview = async (alertId, label) => {
    setIncidentMessage("");
    if (!authToken) {
      setIncidentMessage("Login admin first to review alerts.");
      return;
    }

    const note = (alertActionNotes[alertId] || "").trim();
    setIncidentBusyId(alertId);
    try {
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/review`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ label, note }),
      });
      const body = await res.json();
      if (!res.ok) {
        setIncidentMessage(body.detail || "Alert review failed");
        return;
      }

      upsertAlert(body);
      loadCommunityOverview(communitySinceMinutes, communityImpactProfile);
      if (alertHistoryById[alertId] || expandedHistoryAlertId === alertId) {
        await loadAlertHistory(alertId, { force: true, suppressErrors: true });
      }
      await loadReviewInsights(stationId, sinceMinutes, { suppressErrors: true, silentSuccess: true });
      setAlertActionNotes((previous) => ({ ...previous, [alertId]: "" }));
      setIncidentMessage(
        label === "false_positive"
          ? `Marked ${body.station_id} as false positive${note ? ". Note saved." : "."}`
          : `Confirmed anomaly for ${body.station_id}${note ? ". Note saved." : "."}`
      );
    } catch {
      setIncidentMessage("Cannot reach backend for alert review.");
    } finally {
      setIncidentBusyId("");
    }
  };

  const loadAlertHistory = useCallback(
    async (alertId, options = {}) => {
      const { force = false, suppressErrors = false } = options;
      if (!authToken) {
        if (!suppressErrors) {
          setIncidentMessage("Login admin first to load alert history.");
        }
        return;
      }
      if (!force && alertHistoryById[alertId]) {
        return;
      }

      setHistoryBusyId(alertId);
      try {
        const res = await fetch(`${API_BASE}/api/alerts/${alertId}/history?limit=25`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const body = await res.json();
        if (!res.ok) {
          if (!suppressErrors) {
            setIncidentMessage(body.detail || "Alert history load failed");
          }
          return;
        }
        setAlertHistoryById((previous) => ({ ...previous, [alertId]: body }));
      } catch {
        if (!suppressErrors) {
          setIncidentMessage("Cannot reach backend for alert history.");
        }
      } finally {
        setHistoryBusyId("");
      }
    },
    [alertHistoryById, authToken]
  );

  const toggleAlertHistory = useCallback(
    async (alertId) => {
      if (expandedHistoryAlertId === alertId) {
        setExpandedHistoryAlertId("");
        return;
      }
      if (!authToken) {
        setIncidentMessage("Login admin first to load alert history.");
        return;
      }
      setExpandedHistoryAlertId(alertId);
      await loadAlertHistory(alertId);
    },
    [authToken, expandedHistoryAlertId, loadAlertHistory]
  );

  const runReviewedAlertExport = async () => {
    setReviewExportMessage("");
    if (!authToken) {
      setReviewExportMessage("Login admin first to export labeled alerts.");
      return;
    }

    setReviewExportBusy(true);
    try {
      const params = new URLSearchParams({
        format: "csv",
        since_minutes: String(sinceMinutes),
        limit: "1000",
      });
      if (stationId !== "all") {
        params.set("station_id", stationId);
      }

      const res = await fetch(`${API_BASE}/api/alerts/labeled/export?${params.toString()}`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        let detail = "Alert export failed";
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch {
          // Ignore parse failures and keep the default message.
        }
        setReviewExportMessage(detail);
        return;
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const disposition = res.headers.get("content-disposition") || "";
      const filenameMatch = disposition.match(/filename=\"?([^"]+)\"?/i);
      anchor.href = url;
      anchor.download = filenameMatch?.[1] || "anomalyguard-labeled-alerts.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      setReviewExportMessage("Downloaded labeled alerts export.");
    } catch {
      setReviewExportMessage("Cannot reach backend for labeled alert export.");
    } finally {
      setReviewExportBusy(false);
    }
  };

  const runRetrainingPreparation = async () => {
    setRetrainingJobMessage("");
    if (!authToken) {
      setRetrainingJobMessage("Login admin first to prepare a retraining bundle.");
      return;
    }

    setRetrainingJobBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/alerts/labeled/retraining-jobs`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          station_id: stationId === "all" ? null : stationId,
          since_minutes: sinceMinutes,
          limit: 1000,
          recent_count: 50,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setRetrainingJobMessage(body.detail || "Retraining preparation failed to start.");
        return;
      }

      const jobId = body.id;
      let jobFinished = false;
      setRetrainingJobMessage(`Retraining bundle job queued (${jobId}).`);

      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));

        const jobRes = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
          headers: { Authorization: `Bearer ${authToken}` },
        });
        const jobBody = await jobRes.json();
        if (!jobRes.ok) {
          setRetrainingJobMessage(jobBody.detail || "Cannot read retraining job status.");
          break;
        }

        if (jobBody.status === "queued") {
          setRetrainingJobMessage(`Retraining bundle job queued (${jobId}).`);
          continue;
        }
        if (jobBody.status === "running") {
          setRetrainingJobMessage(`Retraining bundle job running (${jobId})...`);
          continue;
        }
        if (jobBody.status === "failed") {
          setRetrainingJobMessage(jobBody.error_message || "Retraining bundle job failed.");
          jobFinished = true;
          break;
        }
        if (jobBody.status === "succeeded") {
          const result = jobBody.result_payload || {};
          setLastRetrainingBundle(result);
          await loadReviewInsights(stationId, sinceMinutes, { suppressErrors: true, silentSuccess: true });
          const manifestId = result.manifest?.manifest_id || "training bundle";
          const recommendation = result.recommendation || "hold";
          const mlflowSuffix = result.mlflow_run_id ? ` MLflow ${result.mlflow_run_id}.` : "";
          setRetrainingJobMessage(
            `Prepared ${manifestId} with recommendation ${recommendation}.${mlflowSuffix}`
          );
          jobFinished = true;
          break;
        }
      }

      if (!jobFinished) {
        setRetrainingJobMessage(`Retraining bundle job still running (${jobId}). Check again shortly.`);
      }
    } catch {
      setRetrainingJobMessage("Cannot reach backend for retraining bundle preparation.");
    } finally {
      setRetrainingJobBusy(false);
    }
  };

  const filteredReadings = useMemo(() => {
    if (stationId === "all") return readings;
    return readings.filter((reading) => reading.station_id === stationId);
  }, [readings, stationId]);

  const filteredAlerts = useMemo(() => {
    if (stationId === "all") return alerts;
    return alerts.filter((alert) => alert.station_id === stationId);
  }, [alerts, stationId]);

  const latest = filteredReadings[filteredReadings.length - 1];
  const chartData = useMemo(
    () =>
      filteredReadings.map((reading) => ({
        t: new Date(reading.timestamp).toLocaleTimeString(),
        turbidity: reading.turbidity,
        tds: reading.tds,
        ph: reading.ph,
      })),
    [filteredReadings]
  );

  const selectedTelemetry = selectedDeviceStatus?.telemetry || {};
  const inferredFields = selectedTelemetry.inferred_fields || [];
  const deviceLastSeen = selectedDeviceStatus?.last_seen_at
    ? new Date(selectedDeviceStatus.last_seen_at).toLocaleString()
    : "No telemetry yet";

  return (
    <div className="shell">
      <header className="shellHeader">
        <div>
          <p className="eyebrow">AnomalyGuard</p>
          <h1 className="shellTitle">Water Risk Intelligence</h1>
        </div>
        <div className="headerActions">
          <nav className="routeNav" aria-label="Primary">
            <button className={route === OPS_PATH ? "routeButton active" : "routeButton"} onClick={() => navigate(OPS_PATH)}>
              Ops View
            </button>
            <button
              className={route === COMMUNITY_PATH ? "routeButton active" : "routeButton"}
              onClick={() => navigate(COMMUNITY_PATH)}
            >
              Community View
            </button>
          </nav>
          <span className={connected ? "badge ok" : "badge err"}>{connected ? "Realtime Connected" : "Disconnected"}</span>
        </div>
      </header>

      {route === COMMUNITY_PATH ? (
        <CommunityView
          communityOverview={communityOverview}
          communityImpactProfiles={communityImpactProfiles}
          communityImpactProfile={communityImpactProfile}
          communitySinceMinutes={communitySinceMinutes}
          onCommunityImpactProfileChange={setCommunityImpactProfile}
          onCommunityWindowChange={setCommunitySinceMinutes}
        />
      ) : (
        <OpsView
          connected={connected}
          meta={meta}
          username={username}
          password={password}
          authMessage={authMessage}
          onUsernameChange={setUsername}
          onPasswordChange={setPassword}
          onLogin={runLogin}
          stations={stations}
          stationId={stationId}
          onStationChange={setStationId}
          sinceMinutes={sinceMinutes}
          onSinceMinutesChange={setSinceMinutes}
          vnIngestStation={vnIngestStation}
          onVnStationChange={setVnIngestStation}
          onRunIngest={runVNIngest}
          ingesting={ingesting}
          ingestMessage={ingestMessage}
          authToken={authToken}
          deviceStations={deviceStations}
          deviceStationId={deviceStationId}
          onDeviceStationChange={(nextStationId) => {
            setDeviceStationId(nextStationId);
            setControlDirty(false);
          }}
          selectedDeviceStatus={selectedDeviceStatus}
          selectedTelemetry={selectedTelemetry}
          deviceLastSeen={deviceLastSeen}
          inferredFields={inferredFields}
          deviceControl={deviceControl}
          onDeviceControlPatch={updateDeviceControl}
          onRunDeviceControl={runDeviceControl}
          controlBusy={controlBusy}
          deviceMessage={deviceMessage}
          latest={latest}
          chartData={chartData}
          filteredAlerts={filteredAlerts}
          onIncidentAction={runIncidentAction}
          onReviewAction={runAlertReview}
          alertActionNotes={alertActionNotes}
          onAlertNoteChange={(alertId, note) => {
            setAlertActionNotes((previous) => ({ ...previous, [alertId]: note }));
          }}
          onExportReviewedAlerts={runReviewedAlertExport}
          reviewReadiness={reviewReadiness}
          reviewEvaluation={reviewEvaluation}
          reviewInsightsBusy={reviewInsightsBusy}
          reviewInsightsMessage={reviewInsightsMessage}
          onRefreshReviewInsights={() => loadReviewInsights(stationId, sinceMinutes, { silentSuccess: false })}
          retrainingJobBusy={retrainingJobBusy}
          retrainingJobMessage={retrainingJobMessage}
          lastRetrainingBundle={lastRetrainingBundle}
          onPrepareRetraining={runRetrainingPreparation}
          alertHistoryById={alertHistoryById}
          expandedHistoryAlertId={expandedHistoryAlertId}
          historyBusyId={historyBusyId}
          onToggleAlertHistory={toggleAlertHistory}
          incidentBusyId={incidentBusyId}
          incidentMessage={incidentMessage}
          reviewExportBusy={reviewExportBusy}
          reviewExportMessage={reviewExportMessage}
        />
      )}
    </div>
  );
}

export default App;
