import { communityRiskMeta } from "../lib/risk.js";

function RiskPill({ level }) {
  const meta = communityRiskMeta(level);
  return <span className={`riskPill ${meta.className}`}>{meta.label}</span>;
}

export default RiskPill;
