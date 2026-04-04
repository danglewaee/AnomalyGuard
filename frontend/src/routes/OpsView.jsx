import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import RiskPill from "../components/RiskPill.jsx";
import { DIRECTION_OPTIONS, TIME_WINDOW_OPTIONS, VN_STATIONS } from "../constants.js";
import { alertImpactCopy, communityRiskFromOperatorSeverity, formatTimestamp } from "../lib/risk.js";

function formatHistoryLabel(entry) {
  if (entry.event_type === "detected") {
    return `Alert detected (${entry.event_value})`;
  }
  if (entry.event_type === "incident_status") {
    return `Incident ${entry.event_value}`;
  }
  if (entry.event_type === "review_label") {
    return entry.event_value === "true_anomaly" ? "Marked true anomaly" : "Marked false positive";
  }
  return entry.event_value || entry.event_type;
}

function formatPct(value) {
  if (value == null) return "-";
  return `${Math.round(value * 100)}%`;
}

function formatScore(value) {
  if (value == null) return "-";
  return Number(value).toFixed(3);
}

function driftSummary(metric, asPercent = false) {
  if (!metric || metric.absolute_delta == null) return "-";
  return asPercent ? `${Math.round(metric.absolute_delta * 100)} pts` : formatScore(metric.absolute_delta);
}

function OpsView({
  connected,
  meta,
  username,
  password,
  authMessage,
  onUsernameChange,
  onPasswordChange,
  onLogin,
  stations,
  stationId,
  onStationChange,
  sinceMinutes,
  onSinceMinutesChange,
  vnIngestStation,
  onVnStationChange,
  onRunIngest,
  ingesting,
  ingestMessage,
  authToken,
  deviceStations,
  deviceStationId,
  onDeviceStationChange,
  selectedDeviceStatus,
  selectedTelemetry,
  deviceLastSeen,
  inferredFields,
  deviceControl,
  onDeviceControlPatch,
  onRunDeviceControl,
  controlBusy,
  deviceMessage,
  latest,
  chartData,
  filteredAlerts,
  onIncidentAction,
  onReviewAction,
  alertActionNotes,
  onAlertNoteChange,
  onExportReviewedAlerts,
  reviewReadiness,
  reviewEvaluation,
  reviewInsightsBusy,
  reviewInsightsMessage,
  onRefreshReviewInsights,
  retrainingJobBusy,
  retrainingJobMessage,
  lastRetrainingBundle,
  onPrepareRetraining,
  bundleExportBusy,
  bundleExportMessage,
  onDownloadBundleJson,
  onDownloadBundleExport,
  alertHistoryById,
  expandedHistoryAlertId,
  historyBusyId,
  onToggleAlertHistory,
  incidentBusyId,
  incidentMessage,
  reviewExportBusy,
  reviewExportMessage,
}) {
  const controlTime = `${String(deviceControl.hour).padStart(2, "0")}:${String(deviceControl.minute).padStart(2, "0")}`;

  return (
    <div className="page">
      <section className="pageIntro">
        <div>
          <p className="eyebrow">Operator Console</p>
          <h1>Monitor stations, triage alerts, and coordinate device response</h1>
          <p className="lede">
            This view keeps ingest actions, raw telemetry, and control payloads with the operations team. Community-safe
            messaging now lives in a separate route.
          </p>
        </div>
        <div className="statusStack">
          <div className="statusCard">
            <span className="statusLabel">Realtime</span>
            <strong>{connected ? "Connected" : "Disconnected"}</strong>
          </div>
          <div className="statusCard">
            <span className="statusLabel">Data Source</span>
            <strong>{meta?.data_source || "-"}</strong>
          </div>
          <div className="statusCard">
            <span className="statusLabel">Device Fleet</span>
            <strong>{meta?.counts?.device_states ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="panel authPanel">
        <div>
          <label htmlFor="username">Admin User</label>
          <input id="username" value={username} onChange={(event) => onUsernameChange(event.target.value)} />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(event) => onPasswordChange(event.target.value)} />
        </div>
        <button onClick={onLogin}>Login</button>
        <div className="muted tiny">{authMessage || "Required for ingest and device control."}</div>
      </section>

      <section className="panel controls">
        <div>
          <label htmlFor="station">Station</label>
          <select id="station" value={stationId} onChange={(event) => onStationChange(event.target.value)}>
            <option value="all">All Stations</option>
            {stations.map((station) => (
              <option key={station.station_id} value={station.station_id}>
                {station.station_name} ({station.region})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="window">Time Window</label>
          <select id="window" value={sinceMinutes} onChange={(event) => onSinceMinutesChange(Number(event.target.value))}>
            {TIME_WINDOW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="metaBlock">
          <strong>Note:</strong> {meta?.last_ingest_note || "-"}
          <br />
          <strong>Readings:</strong> {meta?.counts?.readings ?? 0}
          <br />
          <strong>Alerts:</strong> {meta?.counts?.alerts ?? 0}
        </div>
      </section>

      <section className="panel ingestPanel">
        <div>
          <label htmlFor="vnStation">VN Station (Real Feed)</label>
          <select id="vnStation" value={vnIngestStation} onChange={(event) => onVnStationChange(event.target.value)}>
            {VN_STATIONS.map((station) => (
              <option key={station.id} value={station.id}>
                {station.label}
              </option>
            ))}
          </select>
        </div>
        <button onClick={onRunIngest} disabled={ingesting || !authToken}>
          {ingesting ? "Ingesting..." : "Ingest VN Real Data"}
        </button>
        <div className="muted tiny">
          {ingestMessage || "Use this to pull the live VN feed before sharing a public update."}
        </div>
      </section>

      <section className="panel devicePanel">
        <div>
          <label htmlFor="deviceStation">Device Station</label>
          <select id="deviceStation" value={deviceStationId} onChange={(event) => onDeviceStationChange(event.target.value)}>
            <option value="">No device linked</option>
            {deviceStations.map((station) => (
              <option key={station.station_id} value={station.station_id}>
                {station.station_name}
              </option>
            ))}
          </select>
        </div>
        <div className="metaBlock">
          <strong>Last Seen:</strong> {selectedDeviceStatus ? deviceLastSeen : "No device selected"}
          <br />
          <strong>Client:</strong> {selectedTelemetry.client_id || "-"}
          <br />
          <strong>Proxy Fields:</strong> {inferredFields.length > 0 ? inferredFields.join(", ") : "None"}
        </div>
        <div className="deviceStats">
          <MiniStat title="Water Temp" value={selectedTelemetry.water_temp_c != null ? `${selectedTelemetry.water_temp_c} C` : "-"} />
          <MiniStat title="Air Temp" value={selectedTelemetry.ambient_temp_c != null ? `${selectedTelemetry.ambient_temp_c} C` : "-"} />
          <MiniStat title="Humidity" value={selectedTelemetry.humidity != null ? `${selectedTelemetry.humidity}%` : "-"} />
          <MiniStat title="Load Cell" value={selectedTelemetry.weight_g != null ? `${selectedTelemetry.weight_g} g` : "-"} />
        </div>
      </section>

      <section className="panel deviceControlPanel">
        <div>
          <label htmlFor="direction">Direction</label>
          <select id="direction" value={deviceControl.direction} onChange={(event) => onDeviceControlPatch({ direction: Number(event.target.value) })}>
            {DIRECTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="feedTime">Feed Time</label>
          <input
            id="feedTime"
            type="time"
            value={controlTime}
            onChange={(event) => {
              const [hour, minute] = event.target.value.split(":").map(Number);
              onDeviceControlPatch({ hour: hour || 0, minute: minute || 0 });
            }}
          />
        </div>
        <div>
          <label htmlFor="feedWeight">Feed Weight (g)</label>
          <input
            id="feedWeight"
            type="number"
            min="0"
            value={deviceControl.weight}
            onChange={(event) => onDeviceControlPatch({ weight: Number(event.target.value) || 0 })}
          />
        </div>
        <div className="toggleRow">
          <label className={`toggleChip ${deviceControl.pump ? "active" : ""}`}>
            <input type="checkbox" checked={deviceControl.pump} onChange={(event) => onDeviceControlPatch({ pump: event.target.checked })} />
            Pump
          </label>
          <label className={`toggleChip ${deviceControl.isFeeding ? "active" : ""}`}>
            <input
              type="checkbox"
              checked={deviceControl.isFeeding}
              onChange={(event) => onDeviceControlPatch({ isFeeding: event.target.checked })}
            />
            Feeding
          </label>
        </div>
        <button onClick={onRunDeviceControl} disabled={controlBusy || !authToken || !deviceStationId}>
          {controlBusy ? "Updating..." : "Push Device Control"}
        </button>
        <div className="muted tiny">{deviceMessage || "Keep these controls in ops only; do not expose them in public view."}</div>
      </section>

      <section className="cards">
        <Metric title="pH" value={latest ? latest.ph : "-"} />
        <Metric title="TDS" value={latest ? `${latest.tds} ppm` : "-"} />
        <Metric title="Turbidity" value={latest ? `${latest.turbidity} NTU` : "-"} />
        <Metric title="DO" value={latest ? `${latest.do_mg_l} mg/L` : "-"} />
      </section>

      <section className="panel reviewHealthPanel">
        <div className="sectionTitle">
          <div>
            <h2>Reviewed Dataset Health</h2>
            <div className="muted tiny">
              {reviewInsightsMessage ||
                "This panel summarizes whether reviewed alerts are balanced and stable enough for retraining."}
            </div>
            <div className="muted tiny reviewHealthMessage">
              {retrainingJobMessage || "Prepare a retraining bundle once the reviewed dataset looks stable."}
            </div>
          </div>
          <div className="healthActionRow">
            <button className="inlineButton ghost" onClick={onRefreshReviewInsights} disabled={reviewInsightsBusy || !authToken}>
              {reviewInsightsBusy ? "Refreshing..." : "Refresh Health"}
            </button>
            <button className="inlineButton subtle" onClick={onPrepareRetraining} disabled={retrainingJobBusy || !authToken}>
              {retrainingJobBusy ? "Preparing..." : "Prepare Training Run"}
            </button>
          </div>
        </div>

        {!authToken ? (
          <p className="muted">Login admin to load readiness, drift, and threshold evaluation.</p>
        ) : !reviewReadiness || !reviewEvaluation ? (
          <p className="muted">Waiting for reviewed dataset metrics...</p>
        ) : (
          <>
            <div className="healthSummaryGrid">
              <div className="healthStatCard">
                <span>Recommendation</span>
                <strong>{reviewReadiness.recommendation}</strong>
                <div className={`healthBadge health-${reviewReadiness.recommendation}`}>
                  {reviewReadiness.ready_for_training ? "training ready" : "needs operator review"}
                </div>
              </div>
              <div className="healthStatCard">
                <span>Readiness Score</span>
                <strong>{reviewReadiness.readiness_score}</strong>
                <div className="muted tiny">
                  {reviewReadiness.reference_window_count} baseline / {reviewReadiness.recent_window_count} recent
                </div>
              </div>
              <div className="healthStatCard">
                <span>Current Precision</span>
                <strong>{formatPct(reviewEvaluation.current_precision)}</strong>
                <div className="muted tiny">{reviewEvaluation.count} reviewed alerts in scope</div>
              </div>
              <div className="healthStatCard">
                <span>Recommended Threshold</span>
                <strong>{formatScore(reviewEvaluation.recommended_threshold)}</strong>
                <div className="muted tiny">Current alert threshold {formatScore(reviewEvaluation.current_alert_threshold)}</div>
              </div>
            </div>

            <div className="healthGrid">
              <div className="healthCard">
                <h3>Readiness Checks</h3>
                <div className="checkList">
                  {(reviewReadiness.checks || []).map((check) => (
                    <div key={check.key} className={`checkItem ${check.passed ? "passed" : "failed"}`}>
                      <div className="checkItemHead">
                        <strong>{check.key.replaceAll("_", " ")}</strong>
                        <span>{check.passed ? "pass" : "review"}</span>
                      </div>
                      <div className="muted tiny">{check.detail}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="healthCard">
                <h3>Drift Signals</h3>
                <div className="driftGrid">
                  <div className="driftCard">
                    <span>True Label Drift</span>
                    <strong>{driftSummary(reviewReadiness.label_distribution_shift?.true_anomaly, true)}</strong>
                    <div className="muted tiny">
                      {formatPct(reviewReadiness.label_distribution_shift?.true_anomaly?.reference)} baseline to{" "}
                      {formatPct(reviewReadiness.label_distribution_shift?.true_anomaly?.candidate)} recent
                    </div>
                  </div>
                  <div className="driftCard">
                    <span>False Label Drift</span>
                    <strong>{driftSummary(reviewReadiness.label_distribution_shift?.false_positive, true)}</strong>
                    <div className="muted tiny">
                      {formatPct(reviewReadiness.label_distribution_shift?.false_positive?.reference)} baseline to{" "}
                      {formatPct(reviewReadiness.label_distribution_shift?.false_positive?.candidate)} recent
                    </div>
                  </div>
                  <div className="driftCard">
                    <span>Mean Score Shift</span>
                    <strong>{driftSummary(reviewReadiness.mean_score_shift)}</strong>
                    <div className="muted tiny">
                      {formatScore(reviewReadiness.mean_score_shift?.reference)} baseline to{" "}
                      {formatScore(reviewReadiness.mean_score_shift?.candidate)} recent
                    </div>
                  </div>
                  <div className="driftCard">
                    <span>Station Concentration</span>
                    <strong>{driftSummary(reviewReadiness.station_concentration_shift, true)}</strong>
                    <div className="muted tiny">
                      {formatPct(reviewReadiness.station_concentration_shift?.reference)} baseline to{" "}
                      {formatPct(reviewReadiness.station_concentration_shift?.candidate)} recent
                    </div>
                  </div>
                </div>
              </div>

              <div className="healthCard">
                <h3>Label Coverage</h3>
                <div className="healthList">
                  <div className="healthListItem">
                    <span>true_anomaly</span>
                    <strong>{reviewReadiness.label_counts?.true_anomaly ?? 0}</strong>
                  </div>
                  <div className="healthListItem">
                    <span>false_positive</span>
                    <strong>{reviewReadiness.label_counts?.false_positive ?? 0}</strong>
                  </div>
                  {Object.entries(reviewReadiness.station_counts || {}).map(([key, value]) => (
                    <div key={key} className="healthListItem">
                      <span>{key}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="healthCard">
                <h3>Warnings</h3>
                {reviewReadiness.warnings?.length ? (
                  <div className="warningList">
                    {reviewReadiness.warnings.map((warning) => (
                      <div key={warning} className="warningItem">
                        {warning}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="muted tiny">No active warnings for the reviewed dataset.</div>
                )}
              </div>
            </div>

            {lastRetrainingBundle ? (
              <div className="bundleSummary">
                <div className="bundleSummaryCard">
                  <span>Last Prepared Bundle</span>
                  <strong>{lastRetrainingBundle.manifest?.manifest_id || "-"}</strong>
                  <div className="muted tiny">
                    {lastRetrainingBundle.recommendation || "hold"} over {lastRetrainingBundle.manifest?.count ?? 0} reviewed alerts
                  </div>
                </div>
                <div className="bundleSummaryCard">
                  <span>Suggested Split</span>
                  <strong>
                    {lastRetrainingBundle.suggested_split?.train ?? 0}/{lastRetrainingBundle.suggested_split?.validation ?? 0}/
                    {lastRetrainingBundle.suggested_split?.test ?? 0}
                  </strong>
                  <div className="muted tiny">train / validation / test</div>
                </div>
                <div className="bundleSummaryCard">
                  <span>Recommended Threshold</span>
                  <strong>{formatScore(lastRetrainingBundle.recommended_threshold)}</strong>
                  <div className="muted tiny">{lastRetrainingBundle.mlflow_run_id || "No MLflow run id available"}</div>
                </div>
              </div>
            ) : null}

            {lastRetrainingBundle ? (
              <div className="bundleActions">
                <button className="inlineButton ghost" onClick={onDownloadBundleJson} disabled={bundleExportBusy}>
                  {bundleExportBusy ? "Working..." : "Download Bundle JSON"}
                </button>
                <button className="inlineButton ghost" onClick={() => onDownloadBundleExport("json")} disabled={bundleExportBusy}>
                  {bundleExportBusy ? "Working..." : "Reviewed JSON"}
                </button>
                <button className="inlineButton subtle" onClick={() => onDownloadBundleExport("csv")} disabled={bundleExportBusy}>
                  {bundleExportBusy ? "Working..." : "Reviewed CSV"}
                </button>
                <div className="muted tiny bundleExportMessage">
                  {bundleExportMessage || "Export the exact reviewed dataset that was used to prepare this bundle."}
                </div>
              </div>
            ) : null}
          </>
        )}
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
          <div className="sectionTitle">
            <div>
              <h2>Recent Alerts</h2>
              <div className="muted tiny alertGuide">{incidentMessage || "Acknowledge active alerts, then resolve them once the field check is complete."}</div>
              <div className="muted tiny exportGuide">{reviewExportMessage || "Export reviewed alerts to create a supervised feedback dataset."}</div>
            </div>
            <button className="inlineButton subtle" onClick={onExportReviewedAlerts} disabled={reviewExportBusy || !authToken}>
              {reviewExportBusy ? "Exporting..." : "Export Reviewed Alerts"}
            </button>
          </div>
          <div className="alerts">
            {filteredAlerts.length === 0 && <p className="muted">No anomalies in selected scope.</p>}
            {filteredAlerts.map((alert) => {
              const incidentStatus = alert.incident_status || "open";
              const isBusy = incidentBusyId === alert.id;
              const isHistoryBusy = historyBusyId === alert.id;
              const isHistoryOpen = expandedHistoryAlertId === alert.id;
              const history = alertHistoryById[alert.id] || [];
              const noteValue = alertActionNotes[alert.id] || "";
              const reviewLabel = alert.review_label || "";

              return (
                <div key={alert.id} className={`alertItem sev-${alert.severity}`}>
                  <div className="alertHead">
                    <strong>{alert.severity.toUpperCase()}</strong>
                    <span>score: {alert.score}</span>
                  </div>
                  <div className="alertMeta">
                    <RiskPill level={communityRiskFromOperatorSeverity(alert.severity)} />
                    <span>{alert.station_id}</span>
                  </div>
                  <div className="alertReasons">{(alert.reasons || []).join(", ") || "anomalous pattern"}</div>
                  <p className="alertImpact">{alertImpactCopy(alert)}</p>
                  <div className="incidentMetaRow">
                    <span className={`incidentBadge incident-${incidentStatus}`}>{incidentStatus}</span>
                    <span className="muted tiny">{formatTimestamp(alert.incident_updated_at || alert.timestamp)}</span>
                  </div>
                  {reviewLabel ? (
                    <div className="incidentMetaRow">
                      <span className={`reviewBadge review-${reviewLabel}`}>{reviewLabel === "true_anomaly" ? "true anomaly" : "false positive"}</span>
                      <span className="muted tiny">{formatTimestamp(alert.reviewed_at || alert.timestamp)}</span>
                    </div>
                  ) : null}
                  {alert.incident_note ? <div className="muted tiny">{alert.incident_note}</div> : null}
                  {alert.review_note ? <div className="muted tiny">{alert.review_note}</div> : null}
                  <div className="noteComposer">
                    <label className="muted tiny" htmlFor={`alert-note-${alert.id}`}>
                      Operator note
                    </label>
                    <input
                      id={`alert-note-${alert.id}`}
                      value={noteValue}
                      onChange={(event) => onAlertNoteChange(alert.id, event.target.value)}
                      placeholder="Add a field note before triage or review"
                    />
                  </div>
                  <div className="incidentActions">
                    {incidentStatus === "open" ? (
                      <button className="inlineButton" onClick={() => onIncidentAction(alert.id, "acknowledge")} disabled={isBusy || !authToken}>
                        {isBusy ? "Updating..." : "Acknowledge"}
                      </button>
                    ) : null}
                    {incidentStatus === "acknowledged" ? (
                      <button className="inlineButton secondary" onClick={() => onIncidentAction(alert.id, "resolve")} disabled={isBusy || !authToken}>
                        {isBusy ? "Updating..." : "Resolve"}
                      </button>
                    ) : null}
                    {incidentStatus === "resolved" ? (
                      <button className="inlineButton ghost" onClick={() => onIncidentAction(alert.id, "reopen")} disabled={isBusy || !authToken}>
                        {isBusy ? "Updating..." : "Reopen"}
                      </button>
                    ) : null}
                    <button
                      className={`inlineButton subtle ${reviewLabel === "true_anomaly" ? "selected" : ""}`}
                      onClick={() => onReviewAction(alert.id, "true_anomaly")}
                      disabled={isBusy || !authToken}
                    >
                      {isBusy && reviewLabel !== "true_anomaly" ? "Updating..." : "True Anomaly"}
                    </button>
                    <button
                      className={`inlineButton ghost ${reviewLabel === "false_positive" ? "selected" : ""}`}
                      onClick={() => onReviewAction(alert.id, "false_positive")}
                      disabled={isBusy || !authToken}
                    >
                      {isBusy && reviewLabel !== "false_positive" ? "Updating..." : "False Positive"}
                    </button>
                    <button className="inlineButton ghost" onClick={() => onToggleAlertHistory(alert.id)} disabled={isHistoryBusy}>
                      {isHistoryBusy ? "Loading..." : isHistoryOpen ? "Hide History" : "Show History"}
                    </button>
                  </div>
                  {isHistoryOpen ? (
                    <div className="historyPanel">
                      {isHistoryBusy ? (
                        <div className="muted tiny">Loading operator timeline...</div>
                      ) : history.length === 0 ? (
                        <div className="muted tiny">No operator history recorded for this alert yet.</div>
                      ) : (
                        history.map((entry) => (
                          <div key={`${alert.id}-history-${entry.id}`} className="historyEntry">
                            <div className="historyEntryHead">
                              <strong className="historyTitle">{formatHistoryLabel(entry)}</strong>
                              <span className="muted tiny">{formatTimestamp(entry.created_at)}</span>
                            </div>
                            <div className="muted tiny">
                              {entry.changed_by || "system"} | {entry.station_id}
                            </div>
                            {entry.note ? <div className="historyNote">{entry.note}</div> : null}
                          </div>
                        ))
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })}
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

function MiniStat({ title, value }) {
  return (
    <div className="miniCard">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default OpsView;
