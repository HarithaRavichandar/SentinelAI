import { useState, useMemo, useCallback, useEffect } from "react";
import { getHealth } from "../api";
import { useAlertStats, AlertRecord } from "./AlertStatsContext";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

/* ================================================================== */
/*  Constants                                                          */
/* ================================================================== */

const CLASS_MAP: Record<number, string> = {
  0: "Benign",
  1: "Bot",
  2: "BruteForce",
  3: "DDoS",
  4: "DoS",
  5: "FTP-Patator",
  6: "Infiltration",
  7: "PortScan",
  8: "SSH-Patator",
  9: "Worms",
};

const CLASS_COLORS: Record<string, string> = {
  Benign: "#10b981",
  Bot: "#f59e0b",
  BruteForce: "#ef4444",
  DDoS: "#8b5cf6",
  DoS: "#ec4899",
  "FTP-Patator": "#f97316",
  Infiltration: "#06b6d4",
  PortScan: "#3b82f6",
  "SSH-Patator": "#14b8a6",
  Worms: "#e11d48",
};

const DEFAULT_COLORS = [
  "#6366f1", "#a78bfa", "#c084fc", "#e879f9",
  "#f472b6", "#fb7185", "#f87171", "#fbbf24",
];

const SOURCE_COLORS = {
  triage: "#3b82f6",
  live: "#10b981",
  batch: "#f59e0b",
};

const SOURCE_LABELS = {
  triage: "Alert Triage",
  live: "Live Capture",
  batch: "Batch Upload",
};

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

function getPredictedScore(a: AlertRecord): number | null {
  if (typeof a.predicted_score === "number") return a.predicted_score;
  if (a.decision && typeof a.decision.decision_confidence === "number")
    return a.decision.decision_confidence;
  if (!a.probabilities) return null;
  const probs = Array.isArray(a.probabilities)
    ? a.probabilities
    : Object.values(a.probabilities);
  if (probs.length === 0) return null;
  const idx = a.class_id;
  return typeof probs[idx] === "number" ? probs[idx] : Math.max(...probs);
}

function getPriorityInfo(a: AlertRecord) {
  const p =
    a.priority ||
    a.decision?.priority ||
    "unknown";
  const pl = p.toLowerCase();
  if (pl === "critical")
    return { label: "Critical", color: "#ef4444", bg: "rgba(239,68,68,0.12)" };
  if (pl === "high")
    return { label: "High", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" };
  if (pl === "medium")
    return { label: "Medium", color: "#3b82f6", bg: "rgba(59,130,246,0.12)" };
  if (pl === "low")
    return { label: "Low", color: "#10b981", bg: "rgba(16,185,129,0.12)" };
  return { label: "Unknown", color: "#64748b", bg: "rgba(100,116,139,0.12)" };
}

function getSourceBadge(source?: string) {
  const s = (source || "triage") as keyof typeof SOURCE_COLORS;
  return { label: SOURCE_LABELS[s] || s, color: SOURCE_COLORS[s] || "#64748b" };
}

function generateAlertsCsv(alerts: AlertRecord[]): string {
  const headers = [
    "ID", "Timestamp", "Source", "Class ID", "Class Label", "Score",
    "Priority", "Alert Status", "Review Status", "Recommended Action", "Policy",
  ];
  const rows = alerts.map((a) => {
    const score = getPredictedScore(a);
    const label = a.class_label || CLASS_MAP[a.class_id] || `Class ${a.class_id}`;
    return [
      a.id ?? "",
      a.timestamp,
      a.source || "triage",
      a.class_id,
      label,
      score !== null ? score.toFixed(4) : "",
      a.priority || a.decision?.priority || "",
      a.alert_status || "new",
      a.decision?.decision_status || "",
      a.decision?.recommended_action || a.recommended_action || "",
      a.decision?.policy_mode || a.policy_mode || "",
    ].join(",");
  });
  return [headers.join(","), ...rows].join("\n");
}

function downloadCsv(csv: string, filename: string) {
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function generatePdfReport(
  alerts: AlertRecord[],
  priorityCounts: { critical: number; high: number; medium: number; low: number },
  classificationData: { name: string; count: number }[],
  sourceBreakdown: { triage: number; live: number; batch: number },
) {
  const now = new Date();
  const totalAlerts = alerts.length;
  const attackAlerts = alerts.filter((a) => a.class_id !== 0).length;
  const benignAlerts = totalAlerts - attackAlerts;
  const attackPct = totalAlerts > 0 ? ((attackAlerts / totalAlerts) * 100).toFixed(1) : "0";

  const topThreats = [...classificationData]
    .filter((c) => c.name !== "Benign" && c.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  const criticalAlerts = alerts
    .filter((a) => (a.priority || a.decision?.priority || "").toLowerCase() === "critical")
    .slice(0, 10);

  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>SentinelAI Security Report — ${now.toLocaleDateString()}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a2e; padding: 40px; max-width: 900px; margin: 0 auto; line-height: 1.5; }
  h1 { font-size: 1.8rem; margin-bottom: 4px; color: #0d0d2b; }
  .subtitle { color: #64748b; font-size: 0.9rem; margin-bottom: 32px; }
  h2 { font-size: 1.15rem; color: #1e293b; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; text-align: center; }
  .kpi-value { font-size: 1.8rem; font-weight: 700; }
  .kpi-label { font-size: 0.8rem; color: #64748b; margin-top: 4px; }
  .priority-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .priority-card { padding: 12px; border-radius: 6px; text-align: center; color: #fff; }
  .priority-card .num { font-size: 1.5rem; font-weight: 700; }
  .priority-card .lbl { font-size: 0.75rem; text-transform: uppercase; opacity: 0.9; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-bottom: 20px; }
  th { background: #f1f5f9; padding: 8px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #cbd5e1; }
  td { padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }
  tr:nth-child(even) td { background: #f8fafc; }
  .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
  .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 0.75rem; text-align: center; }
  @media print { body { padding: 20px; } .no-print { display: none; } }
</style>
</head><body>
<h1>🛡️ SentinelAI — Security Operations Report</h1>
<p class="subtitle">Generated: ${now.toLocaleString()} · Covering ${totalAlerts} alerts across all sources</p>

<div class="no-print" style="margin-bottom:24px">
  <button onclick="window.print()" style="background:#3b82f6;color:#fff;border:none;padding:10px 24px;border-radius:6px;font-size:0.95rem;cursor:pointer">
    🖨️ Print / Save as PDF
  </button>
</div>

<h2>Executive Summary</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="kpi-value">${totalAlerts}</div><div class="kpi-label">Total Alerts</div></div>
  <div class="kpi"><div class="kpi-value" style="color:#ef4444">${attackAlerts}</div><div class="kpi-label">Attack Alerts (${attackPct}%)</div></div>
  <div class="kpi"><div class="kpi-value" style="color:#10b981">${benignAlerts}</div><div class="kpi-label">Benign</div></div>
  <div class="kpi"><div class="kpi-value" style="color:#ef4444">${priorityCounts.critical}</div><div class="kpi-label">Critical</div></div>
</div>

<h2>Priority Breakdown</h2>
<div class="priority-grid">
  <div class="priority-card" style="background:#ef4444"><div class="num">${priorityCounts.critical}</div><div class="lbl">Critical</div></div>
  <div class="priority-card" style="background:#f59e0b"><div class="num">${priorityCounts.high}</div><div class="lbl">High</div></div>
  <div class="priority-card" style="background:#3b82f6"><div class="num">${priorityCounts.medium}</div><div class="lbl">Medium</div></div>
  <div class="priority-card" style="background:#10b981"><div class="num">${priorityCounts.low}</div><div class="lbl">Low</div></div>
</div>

<h2>Source Breakdown</h2>
<table>
  <thead><tr><th>Source</th><th>Alert Count</th><th>% of Total</th></tr></thead>
  <tbody>
    <tr><td>🔍 Alert Triage</td><td>${sourceBreakdown.triage}</td><td>${totalAlerts > 0 ? ((sourceBreakdown.triage / totalAlerts) * 100).toFixed(1) : 0}%</td></tr>
    <tr><td>📡 Live Capture</td><td>${sourceBreakdown.live}</td><td>${totalAlerts > 0 ? ((sourceBreakdown.live / totalAlerts) * 100).toFixed(1) : 0}%</td></tr>
    <tr><td>📦 Batch Upload</td><td>${sourceBreakdown.batch}</td><td>${totalAlerts > 0 ? ((sourceBreakdown.batch / totalAlerts) * 100).toFixed(1) : 0}%</td></tr>
  </tbody>
</table>

<h2>Top Threat Categories</h2>
<table>
  <thead><tr><th>#</th><th>Threat Type</th><th>Count</th><th>% of Attacks</th></tr></thead>
  <tbody>
    ${topThreats.map((t, i) => `<tr><td>${i + 1}</td><td>${t.name}</td><td>${t.count}</td><td>${attackAlerts > 0 ? ((t.count / attackAlerts) * 100).toFixed(1) : 0}%</td></tr>`).join("")}
    ${topThreats.length === 0 ? '<tr><td colspan="4" style="text-align:center;color:#94a3b8">No attack alerts detected</td></tr>' : ""}
  </tbody>
</table>

${criticalAlerts.length > 0 ? `
<h2>⚠️ Critical Alerts (Recent ${Math.min(criticalAlerts.length, 10)})</h2>
<table>
  <thead><tr><th>Time</th><th>Class</th><th>Score</th><th>Source</th><th>Action</th></tr></thead>
  <tbody>
    ${criticalAlerts.map((a) => {
    const score = getPredictedScore(a);
    const label = a.class_label || CLASS_MAP[a.class_id] || "Class " + a.class_id;
    const action = a.decision?.recommended_action || a.recommended_action || "—";
    return `<tr><td>${new Date(a.timestamp).toLocaleString()}</td><td>${label}</td><td>${score !== null ? score.toFixed(4) : "—"}</td><td>${a.source || "triage"}</td><td>${action.replace(/_/g, " ")}</td></tr>`;
  }).join("")}
  </tbody>
</table>` : ""}

<div class="footer">
  SentinelAI — AI-Powered Network Security Alert Triage · Report auto-generated · ${now.toISOString()}
</div>
</body></html>`;

  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  // Clean up after a delay
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

/* ================================================================== */
/*  Sub-Components                                                     */
/* ================================================================== */

function StatCard({
  label,
  value,
  sub,
  color,
  icon,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="dash-stat-card">
      <div className="dash-stat-icon" style={{ color }}>
        {icon}
      </div>
      <div className="dash-stat-body">
        <div className="dash-stat-value" style={{ color }}>{value}</div>
        <div className="dash-stat-label">{label}</div>
        {sub && <div className="dash-stat-sub">{sub}</div>}
      </div>
    </div>
  );
}

function SourcePill({ source }: { source?: string }) {
  const { label, color } = getSourceBadge(source);
  return (
    <span
      className="dash-source-pill"
      style={{ color, borderColor: `${color}33`, background: `${color}0d` }}
    >
      {label}
    </span>
  );
}

function PriorityBadge({ alert }: { alert: AlertRecord }) {
  const { label, color, bg } = getPriorityInfo(alert);
  return (
    <span
      className="dash-priority-badge"
      style={{ color, background: bg, borderColor: `${color}33` }}
    >
      {label}
    </span>
  );
}

/* ================================================================== */
/*  Alert Grouping / Correlation                                       */
/* ================================================================== */

interface AlertGroup {
  id: string;
  label: string;
  priority: string;
  count: number;
  firstSeen: string;
  lastSeen: string;
  sources: Set<string>;
  alerts: AlertRecord[];
}

const GROUP_WINDOW_MS = 5 * 60 * 1000; // 5-minute window

function groupAlerts(alerts: AlertRecord[]): AlertGroup[] {
  if (alerts.length === 0) return [];

  // Sort by time
  const sorted = [...alerts].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const groups: AlertGroup[] = [];
  const openGroups = new Map<string, AlertGroup>(); // key: class_label

  for (const a of sorted) {
    const label = a.class_label || CLASS_MAP[a.class_id] || `Class ${a.class_id}`;
    if (label === "Benign") continue; // skip benign from grouping

    const t = new Date(a.timestamp).getTime();
    const existing = openGroups.get(label);

    if (existing) {
      const lastT = new Date(existing.lastSeen).getTime();
      if (t - lastT <= GROUP_WINDOW_MS) {
        // Extend the group
        existing.count++;
        existing.lastSeen = a.timestamp;
        existing.sources.add(a.source || "triage");
        existing.alerts.push(a);
        // Escalate priority: keep highest
        const pOrder = ["critical", "high", "medium", "low"];
        const curIdx = pOrder.indexOf(existing.priority);
        const newIdx = pOrder.indexOf((a.priority || a.decision?.priority || "medium").toLowerCase());
        if (newIdx >= 0 && (curIdx < 0 || newIdx < curIdx)) {
          existing.priority = pOrder[newIdx];
        }
        continue;
      } else {
        // Close old group, start new
        groups.push(existing);
        openGroups.delete(label);
      }
    }

    // New group
    const priority = (a.priority || a.decision?.priority || "medium").toLowerCase();
    const sources = new Set<string>();
    sources.add(a.source || "triage");
    openGroups.set(label, {
      id: `grp-${label}-${t}`,
      label,
      priority,
      count: 1,
      firstSeen: a.timestamp,
      lastSeen: a.timestamp,
      sources,
      alerts: [a],
    });
  }

  // Flush remaining open groups
  for (const g of openGroups.values()) {
    groups.push(g);
  }

  // Sort by most recent first, prioritizing multi-alert groups
  return groups.sort((a, b) => {
    // Groups with more alerts first
    if (b.count !== a.count) return b.count - a.count;
    return new Date(b.lastSeen).getTime() - new Date(a.lastSeen).getTime();
  });
}

function IncidentGroupCard({
  group,
  expanded,
  onToggle,
}: {
  group: AlertGroup;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { color, bg } = getPriorityInfo({ priority: group.priority } as AlertRecord);
  const duration = new Date(group.lastSeen).getTime() - new Date(group.firstSeen).getTime();
  const durationStr =
    duration < 60000
      ? `${Math.round(duration / 1000)}s`
      : duration < 3600000
        ? `${Math.round(duration / 60000)}m`
        : `${(duration / 3600000).toFixed(1)}h`;
  const sourceList = Array.from(group.sources).join(", ");

  return (
    <div className="dash-incident-group" style={{ borderLeftColor: color }}>
      <div className="dash-incident-header" onClick={onToggle}>
        <div className="dash-incident-info">
          <span className="dash-incident-expand">{expanded ? "▼" : "▶"}</span>
          <span
            className="dash-class-badge"
            style={{
              color: CLASS_COLORS[group.label] || "#94a3b8",
              background: `${CLASS_COLORS[group.label] || "#94a3b8"}15`,
              borderColor: `${CLASS_COLORS[group.label] || "#94a3b8"}30`,
            }}
          >
            {group.label}
          </span>
          <span className="dash-incident-count">
            {group.count} alert{group.count !== 1 ? "s" : ""}
          </span>
          <span
            className="dash-priority-badge"
            style={{ color, background: bg, borderColor: `${color}33` }}
          >
            {group.priority}
          </span>
        </div>
        <div className="dash-incident-meta">
          <span className="dash-mono dash-muted">{durationStr} span</span>
          <span className="dash-muted">·</span>
          <span className="dash-muted">{sourceList}</span>
          <span className="dash-muted">·</span>
          <span className="dash-mono dash-muted">
            {new Date(group.lastSeen).toLocaleTimeString()}
          </span>
        </div>
      </div>
      {expanded && (
        <div className="dash-incident-details">
          <table className="dash-table" style={{ margin: 0 }}>
            <thead>
              <tr>
                <th>Time</th>
                <th>Source</th>
                <th>Score</th>
                <th>Priority</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {group.alerts.map((a, i) => {
                const score = getPredictedScore(a);
                const action = a.recommended_action || a.decision?.recommended_action || "—";
                return (
                  <tr key={i}>
                    <td className="dash-mono dash-muted">
                      {new Date(a.timestamp).toLocaleTimeString()}
                    </td>
                    <td><SourcePill source={a.source} /></td>
                    <td className="dash-mono">{score !== null ? score.toFixed(3) : "—"}</td>
                    <td><PriorityBadge alert={a} /></td>
                    <td className="dash-mono dash-muted">
                      {action !== "—" ? action.replace(/_/g, " ") : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Dashboard Component                                                */
/* ================================================================== */

export default function Dashboard() {
  const { alerts, sessionAlerts, liveAlerts, batchAlerts, updateAlertStatus } = useAlertStats();
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [exportNotice, setExportNotice] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  /* Health check */
  useEffect(() => {
    getHealth()
      .then(() => setHealthOk(true))
      .catch(() => setHealthOk(false));
  }, []);

  /* ---- Session metrics (all sources) ---- */
  const triageSessionAlerts = sessionAlerts.filter(
    (a) => !a.source || a.source === "triage"
  );

  const sessionTotal = sessionAlerts.length;
  const sessionBenignCount = sessionAlerts.filter((a) => a.class_id === 0).length;
  const sessionAttackCount = sessionTotal - sessionBenignCount;

  const triageCount = triageSessionAlerts.length;
  const liveCount = liveAlerts.length;
  const batchCount = batchAlerts.length;

  /* Priority counts across ALL session sources */
  const priorityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const a of sessionAlerts) {
      const p = (a.priority || a.decision?.priority || "").toLowerCase();
      if (p in counts) counts[p as keyof typeof counts]++;
    }
    return counts;
  }, [sessionAlerts]);

  /* ---- Classification data ---- */
  const classificationData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [id, name] of Object.entries(CLASS_MAP)) {
      counts[name] = 0;
    }
    for (const a of sessionAlerts) {
      const name = a.class_label || CLASS_MAP[a.class_id] || `Class ${a.class_id}`;
      counts[name] = (counts[name] || 0) + 1;
    }
    return Object.entries(counts).map(([name, count]) => ({
      name,
      count,
      color: CLASS_COLORS[name] || "#6366f1",
      isAttack: name !== "Benign",
    }));
  }, [sessionAlerts]);

  /* ---- Threat distribution (pie) ---- */
  const distributionData = useMemo(() => {
    return classificationData
      .filter((d) => d.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [classificationData]);

  /* ---- Source distribution (pie) ---- */
  const sourceDistribution = useMemo(() => {
    const data: { name: string; value: number; color: string }[] = [];
    if (triageCount > 0)
      data.push({ name: "Alert Triage", value: triageCount, color: SOURCE_COLORS.triage });
    if (liveCount > 0)
      data.push({ name: "Live Capture", value: liveCount, color: SOURCE_COLORS.live });
    if (batchCount > 0)
      data.push({ name: "Batch Upload", value: batchCount, color: SOURCE_COLORS.batch });
    return data;
  }, [triageCount, liveCount, batchCount]);

  /* ---- Timeline ---- */
  const timelineData = useMemo(() => {
    if (sessionAlerts.length === 0) return [];
    const sorted = [...sessionAlerts].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
    const start = new Date(sorted[0].timestamp).getTime();
    const end = new Date(sorted[sorted.length - 1].timestamp).getTime();
    const span = end - start;
    const bucketMs =
      span < 60000 ? 10000 : span < 600000 ? 60000 : span < 3600000 ? 300000 : 900000;
    const buckets = new Map<number, { triage: number; live: number; batch: number }>();
    for (const a of sorted) {
      const t = new Date(a.timestamp).getTime();
      const bk = Math.floor((t - start) / bucketMs) * bucketMs + start;
      if (!buckets.has(bk))
        buckets.set(bk, { triage: 0, live: 0, batch: 0 });
      const b = buckets.get(bk)!;
      const src = (a.source || "triage") as "triage" | "live" | "batch";
      b[src]++;
    }
    return Array.from(buckets.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([ts, counts]) => ({
        time: new Date(ts).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
        ...counts,
        total: counts.triage + counts.live + counts.batch,
      }));
  }, [sessionAlerts]);

  /* ---- Incident groups (correlated alerts) ---- */
  const incidentGroups = useMemo(
    () => groupAlerts(sessionAlerts),
    [sessionAlerts]
  );

  const toggleGroup = useCallback((id: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  /* ---- Filtered alerts for table ---- */
  const filteredAlerts = useMemo(() => {
    return alerts.filter((a) => {
      if (sourceFilter) {
        const src = a.source || "triage";
        if (src !== sourceFilter) return false;
      }
      if (priorityFilter) {
        const p = (a.priority || a.decision?.priority || "").toLowerCase();
        if (priorityFilter === "__unevaluated__") {
          if (p) return false;
        } else if (p !== priorityFilter) return false;
      }
      if (classFilter) {
        const label =
          a.class_label || CLASS_MAP[a.class_id] || `Class ${a.class_id}`;
        if (label !== classFilter) return false;
      }
      if (statusFilter) {
        const st = a.alert_status || "new";
        if (st !== statusFilter) return false;
      }
      if (searchTerm) {
        const s = searchTerm.toLowerCase();
        const haystack = [
          a.class_label,
          CLASS_MAP[a.class_id],
          a.priority,
          a.decision?.priority,
          a.decision?.recommended_action,
          a.recommended_action,
          a.source,
          a.alert_status,
          String(a.id),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(s)) return false;
      }
      return true;
    });
  }, [alerts, searchTerm, priorityFilter, classFilter, sourceFilter, statusFilter]);

  const isFiltered = !!(searchTerm || priorityFilter || classFilter || sourceFilter || statusFilter);
  const clearFilters = () => {
    setSearchTerm("");
    setPriorityFilter("");
    setClassFilter("");
    setSourceFilter("");
    setStatusFilter("");
  };

  const handleExportCsv = useCallback(() => {
    if (filteredAlerts.length === 0) {
      setExportNotice("No alerts match current filters to export.");
      return;
    }
    const csv = generateAlertsCsv(filteredAlerts);
    downloadCsv(csv, `sentinelai_alerts_${Date.now()}.csv`);
    setExportNotice(`Exported ${filteredAlerts.length} alerts to CSV.`);
  }, [filteredAlerts]);

  const handleExportPdf = useCallback(() => {
    if (filteredAlerts.length === 0) {
      setExportNotice("No alerts to include in report.");
      return;
    }
    generatePdfReport(
      filteredAlerts,
      priorityCounts,
      classificationData,
      { triage: triageCount, live: liveCount, batch: batchCount },
    );
    setExportNotice("Report opened — use Print / Save as PDF.");
  }, [filteredAlerts, priorityCounts, classificationData, triageCount, liveCount, batchCount]);

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */

  return (
    <div className="dash-root">
      {/* ---- Header ---- */}
      <div className="dash-header">
        <div>
          <h1 className="dash-h1">Security Operations Dashboard</h1>
          <p className="dash-header-sub">
            Unified view — Alert Triage, Live Capture &amp; Batch Upload
          </p>
        </div>
        <div className="dash-header-right">
          <span
            className="dash-health-dot"
            style={{
              background:
                healthOk === true
                  ? "#10b981"
                  : healthOk === false
                    ? "#ef4444"
                    : "#64748b",
            }}
          />
          <span className="dash-health-text">
            {healthOk === true
              ? "API Connected"
              : healthOk === false
                ? "API Offline"
                : "Checking…"}
          </span>
        </div>
      </div>

      {/* ---- KPI Row ---- */}
      <div className="dash-kpi-row">
        <StatCard
          label="Total Alerts"
          value={sessionTotal}
          sub={`DB: ${alerts.length} records`}
          color="#3b82f6"
          icon={
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11 2v20M2 11h20" strokeLinecap="round" />
            </svg>
          }
        />
        <StatCard
          label="Attacks Detected"
          value={sessionAttackCount}
          sub={`${sessionBenignCount} benign`}
          color="#ef4444"
          icon={
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11 2L2 20h18L11 2z" strokeLinejoin="round" />
              <path d="M11 9v4M11 16h.01" strokeLinecap="round" />
            </svg>
          }
        />
        <StatCard
          label="Critical / High"
          value={`${priorityCounts.critical} / ${priorityCounts.high}`}
          sub={`${priorityCounts.medium} med · ${priorityCounts.low} low`}
          color="#f59e0b"
          icon={
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="9" />
              <path d="M11 7v5l3 3" strokeLinecap="round" />
            </svg>
          }
        />
        <StatCard
          label="Sources Active"
          value={
            (triageCount > 0 ? 1 : 0) +
            (liveCount > 0 ? 1 : 0) +
            (batchCount > 0 ? 1 : 0)
          }
          sub={`T:${triageCount} L:${liveCount} B:${batchCount}`}
          color="#8b5cf6"
          icon={
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="3" />
              <path d="M11 2v4M11 16v4M2 11h4M16 11h4" strokeLinecap="round" />
            </svg>
          }
        />
      </div>

      {/* ---- Charts Row 1: Classification + Source Distribution ---- */}
      <div className="dash-grid-2">
        {/* Classification Breakdown */}
        <div className="dash-card">
          <div className="dash-card-header">
            <h3 className="dash-card-title">Classification Breakdown</h3>
            <div className="dash-card-pills">
              <span className="dash-pill dash-pill-green">Benign: {sessionBenignCount}</span>
              <span className="dash-pill dash-pill-red">Attacks: {sessionAttackCount}</span>
            </div>
          </div>
          <div style={{ width: "100%", height: "320px" }}>
            {sessionTotal === 0 ? (
              <div className="dash-empty-state">
                <div className="dash-empty-icon">📊</div>
                <div className="dash-empty-title">No Session Data</div>
                <p className="dash-empty-desc">
                  Submit flows via Alert Triage, Live Capture, or Batch Upload to see classification data.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart layout="vertical" data={classificationData} margin={{ top: 8, right: 30, left: 10, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} stroke="#475569" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" stroke="#475569" width={105} tick={{ fill: "#cbd5e1", fontSize: 11.5, fontWeight: 500 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", color: "#f8fafc", fontSize: "12px" }}
                    formatter={(val: any, _n: any, item: any) => [
                      `${val} flow${val !== 1 ? "s" : ""} (${item.payload.isAttack ? "Attack" : "Benign"})`,
                      "Count",
                    ]}
                  />
                  <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={14}>
                    {classificationData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} fillOpacity={0.85} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Source Distribution */}
        <div className="dash-card">
          <div className="dash-card-header">
            <h3 className="dash-card-title">Source Distribution</h3>
          </div>
          <div style={{ width: "100%", height: "320px" }}>
            {sourceDistribution.length === 0 ? (
              <div className="dash-empty-state">
                <div className="dash-empty-icon">🔗</div>
                <div className="dash-empty-title">No Source Data</div>
                <p className="dash-empty-desc">
                  Alerts from all three input sources will appear here.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sourceDistribution}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="45%"
                    innerRadius={55}
                    outerRadius={95}
                    paddingAngle={4}
                    stroke="rgba(0,0,0,0.3)"
                    strokeWidth={2}
                  >
                    {sourceDistribution.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", color: "#f8fafc", fontSize: "12px" }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
                    formatter={(value) => <span style={{ color: "#cbd5e1" }}>{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* ---- Charts Row 2: Threat Pie + Timeline ---- */}
      <div className="dash-grid-2">
        {/* Threat Distribution */}
        <div className="dash-card">
          <div className="dash-card-header">
            <h3 className="dash-card-title">Threat Distribution</h3>
          </div>
          <div style={{ width: "100%", height: "320px" }}>
            {distributionData.length === 0 ? (
              <div className="dash-empty-state">
                <div className="dash-empty-icon">🛡️</div>
                <div className="dash-empty-title">No Threats Detected</div>
                <p className="dash-empty-desc">
                  Classification distribution will render as flows are analyzed.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={distributionData}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="45%"
                    innerRadius={55}
                    outerRadius={95}
                    paddingAngle={3}
                    stroke="rgba(0,0,0,0.3)"
                    strokeWidth={2}
                  >
                    {distributionData.map((entry, i) => (
                      <Cell key={i} fill={CLASS_COLORS[entry.name] ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", color: "#f8fafc", fontSize: "12px" }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
                    formatter={(value) => <span style={{ color: "#cbd5e1" }}>{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Activity Timeline (stacked by source) */}
        <div className="dash-card">
          <div className="dash-card-header">
            <h3 className="dash-card-title">Activity Timeline</h3>
          </div>
          <div style={{ width: "100%", height: "320px" }}>
            {timelineData.length === 0 ? (
              <div className="dash-empty-state">
                <div className="dash-empty-icon">⏱️</div>
                <div className="dash-empty-title">No Activity Yet</div>
                <p className="dash-empty-desc">
                  Timeline will populate as alerts arrive from any source.
                </p>
              </div>
            ) : timelineData.length === 1 ? (
              <div className="dash-empty-state">
                <div className="dash-stat-value" style={{ color: "#3b82f6", fontSize: "2rem" }}>
                  {timelineData[0].total}
                </div>
                <div className="dash-empty-title">
                  flow{timelineData[0].total !== 1 ? "s" : ""} at{" "}
                  <span style={{ color: "#38bdf8", fontFamily: "monospace" }}>
                    {timelineData[0].time}
                  </span>
                </div>
                <p className="dash-empty-desc">
                  Trend line renders with 2+ time buckets.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={timelineData} margin={{ top: 15, right: 20, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="time" stroke="#475569" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={20} />
                  <YAxis allowDecimals={false} stroke="#475569" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: "8px", color: "#f8fafc", fontSize: "12px" }}
                  />
                  <Line type="monotone" dataKey="triage" name="Triage" stroke={SOURCE_COLORS.triage} strokeWidth={2} dot={{ fill: SOURCE_COLORS.triage, r: 3 }} />
                  <Line type="monotone" dataKey="live" name="Live" stroke={SOURCE_COLORS.live} strokeWidth={2} dot={{ fill: SOURCE_COLORS.live, r: 3 }} />
                  <Line type="monotone" dataKey="batch" name="Batch" stroke={SOURCE_COLORS.batch} strokeWidth={2} dot={{ fill: SOURCE_COLORS.batch, r: 3 }} />
                  <Legend
                    wrapperStyle={{ fontSize: "11px" }}
                    formatter={(value) => <span style={{ color: "#cbd5e1" }}>{value}</span>}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* ---- Incident Groups (Correlated Alerts) ---- */}
      {incidentGroups.length > 0 && (
        <div className="dash-card">
          <div className="dash-card-header">
            <div>
              <h3 className="dash-card-title">
                🔗 Correlated Incidents
                <span className="dash-pill dash-pill-blue" style={{ marginLeft: "8px", fontSize: "10px" }}>
                  {incidentGroups.length} group{incidentGroups.length !== 1 ? "s" : ""}
                </span>
              </h3>
              <p className="dash-card-desc">
                Alerts grouped by attack type within 5-minute windows
              </p>
            </div>
          </div>
          <div className="dash-incident-list">
            {incidentGroups.slice(0, 20).map((g) => (
              <IncidentGroupCard
                key={g.id}
                group={g}
                expanded={expandedGroups.has(g.id)}
                onToggle={() => toggleGroup(g.id)}
              />
            ))}
          </div>
          {incidentGroups.length > 20 && (
            <p className="dash-table-footer">
              Showing 20 of {incidentGroups.length} incident groups.
            </p>
          )}
        </div>
      )}

      {/* ---- Alert History Table ---- */}
      <div className="dash-card">
        <div className="dash-card-header">
          <div>
            <h3 className="dash-card-title">
              Alert History
              <span className="dash-pill dash-pill-blue" style={{ marginLeft: "8px", fontSize: "10px" }}>
                {filteredAlerts.length} / {alerts.length}
              </span>
            </h3>
            <p className="dash-card-desc">
              Persistent records from SQLite · All sources combined
              {isFiltered && (
                <span className="dash-pill dash-pill-blue" style={{ marginLeft: "8px" }}>
                  Filtered
                </span>
              )}
            </p>
          </div>
          <div className="dash-card-actions">
            <button className="dash-btn dash-btn-secondary" onClick={handleExportCsv}>
              📥 Export CSV
            </button>
            <button className="dash-btn dash-btn-secondary" onClick={handleExportPdf}>
              📄 PDF Report
            </button>
            {isFiltered && (
              <button className="dash-btn dash-btn-ghost" onClick={clearFilters}>
                ✕ Clear
              </button>
            )}
          </div>
        </div>

        {/* Export notice */}
        {exportNotice && (
          <div className={`dash-notice ${exportNotice.includes("No") || exportNotice.includes("Failed") ? "dash-notice-warn" : "dash-notice-ok"}`}>
            <span>{exportNotice}</span>
            <button onClick={() => setExportNotice(null)} className="dash-notice-close">×</button>
          </div>
        )}

        {/* Filters */}
        <div className="dash-filters">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search alerts…"
            className="dash-input"
          />
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="dash-input">
            <option value="">All Sources</option>
            <option value="triage">Alert Triage</option>
            <option value="live">Live Capture</option>
            <option value="batch">Batch Upload</option>
          </select>
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} className="dash-input">
            <option value="">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={classFilter} onChange={(e) => setClassFilter(e.target.value)} className="dash-input">
            <option value="">All Classes</option>
            {Object.values(CLASS_MAP).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="dash-input">
            <option value="">All Statuses</option>
            <option value="new">🆕 New</option>
            <option value="acknowledged">👁️ Acknowledged</option>
            <option value="investigating">🔍 Investigating</option>
            <option value="resolved">✅ Resolved</option>
            <option value="false_positive">🚫 False Positive</option>
          </select>
        </div>

        {/* Table */}
        {alerts.length === 0 ? (
          <p className="dash-table-empty">No alerts recorded yet.</p>
        ) : filteredAlerts.length === 0 ? (
          <div className="dash-empty-state" style={{ margin: "1rem 0" }}>
            <div className="dash-empty-icon">🔍</div>
            <div className="dash-empty-title">No matches</div>
            <p className="dash-empty-desc">Try adjusting your filters.</p>
            <button className="dash-btn dash-btn-primary" onClick={clearFilters}>
              Clear Filters
            </button>
          </div>
        ) : (
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Time</th>
                  <th>Source</th>
                  <th>Class</th>
                  <th>Score</th>
                  <th>Priority</th>
                  <th>Action</th>
                  <th>Status</th>
                  <th style={{ textAlign: "center" }}>→</th>
                </tr>
              </thead>
              <tbody>
                {filteredAlerts.slice(0, 100).map((a, idx) => {
                  const score = getPredictedScore(a);
                  const label =
                    a.class_label ||
                    CLASS_MAP[a.class_id] ||
                    `Class ${a.class_id}`;
                  const action =
                    a.recommended_action ||
                    a.decision?.recommended_action ||
                    "—";
                  return (
                    <tr key={a.id ?? idx}>
                      <td className="dash-mono dash-muted">
                        {a.id != null ? `#${a.id}` : "—"}
                      </td>
                      <td className="dash-mono dash-muted" title={new Date(a.timestamp).toISOString()}>
                        {new Date(a.timestamp).toLocaleTimeString()}
                      </td>
                      <td>
                        <SourcePill source={a.source} />
                      </td>
                      <td>
                        <span
                          className="dash-class-badge"
                          style={{
                            color: CLASS_COLORS[label] || "#94a3b8",
                            background: `${CLASS_COLORS[label] || "#94a3b8"}15`,
                            borderColor: `${CLASS_COLORS[label] || "#94a3b8"}30`,
                          }}
                        >
                          {label}
                        </span>
                      </td>
                      <td className="dash-mono">
                        {score !== null ? score.toFixed(3) : "—"}
                      </td>
                      <td>
                        <PriorityBadge alert={a} />
                      </td>
                      <td className="dash-mono dash-muted" style={{ maxWidth: "180px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {action !== "—" ? action.replace(/_/g, " ") : "—"}
                      </td>
                      <td>
                        <select
                          className="dash-status-select"
                          value={a.alert_status || "new"}
                          onChange={(e) => {
                            const key = a.id ? `id-${a.id}` : `${a.timestamp}-${a.class_id}`;
                            updateAlertStatus(key, e.target.value as AlertRecord["alert_status"]);
                          }}
                        >
                          <option value="new">🆕 New</option>
                          <option value="acknowledged">👁️ Ack</option>
                          <option value="investigating">🔍 Investigating</option>
                          <option value="resolved">✅ Resolved</option>
                          <option value="false_positive">🚫 False Pos</option>
                        </select>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <a href="/triage" className="dash-link">Triage</a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {filteredAlerts.length > 100 && (
          <p className="dash-table-footer">
            Showing 100 of {filteredAlerts.length} alerts. Export CSV for full dataset.
          </p>
        )}
      </div>
    </div>
  );
}