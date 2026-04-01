const COMMUNITY_RISK_META = {
  stable: {
    label: "Stable",
    className: "stable",
    summary: "No urgent community action is indicated right now.",
  },
  watch: {
    label: "Watch",
    className: "watch",
    summary: "Early warning signs need a closer look.",
  },
  warning: {
    label: "Warning",
    className: "warning",
    summary: "Operators should verify this area quickly.",
  },
  critical: {
    label: "Critical",
    className: "critical",
    summary: "Immediate verification and public-safe guidance are needed.",
  },
};

export function communityRiskMeta(level) {
  return COMMUNITY_RISK_META[level] || COMMUNITY_RISK_META.stable;
}

export function communityRiskFromOperatorSeverity(severity) {
  if (severity === "high") return "critical";
  if (severity === "medium") return "warning";
  return "watch";
}

export function alertImpactCopy(alert) {
  const reasons = (alert.reasons || []).map((item) => item.toLowerCase());

  if (reasons.some((item) => item.includes("turbidity"))) {
    return "Cloudy or sediment-heavy water can affect direct intake quality and stress nearby ponds.";
  }
  if (reasons.some((item) => item.includes("do_mg_l"))) {
    return "Low dissolved oxygen can stress fish and other aquatic life very quickly.";
  }
  if (reasons.some((item) => item.includes("ph"))) {
    return "Rapid acidity shifts can make untreated water riskier for households and aquaculture.";
  }
  if (reasons.some((item) => item.includes("tds"))) {
    return "Higher dissolved solids can reduce intake quality for sensitive uses.";
  }
  if (alert.severity === "high") {
    return "This pattern should be verified fast before downstream communities pay the price.";
  }
  if (alert.severity === "medium") {
    return "This station needs a quick operator check before conditions worsen.";
  }
  return "Keep this site under closer watch while fresh readings arrive.";
}

export function formatTimestamp(value) {
  if (!value) return "No update yet";
  return new Date(value).toLocaleString();
}
