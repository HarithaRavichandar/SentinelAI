import { useState, useRef, useCallback, useEffect } from "react";
import { fetchCaptureInterfaces, fetchPcapStatus, getWsBase } from "../api";
import LoadingSpinner from "./LoadingSpinner";
import ErrorMessage from "./ErrorMessage";

/* ================================================================== */
/*  Types                                                              */
/* ================================================================== */

interface NetworkInterface {
  name: string;
  addresses: string[];
  is_up: boolean;
}

interface FlowSummary {
  src_ip: string;
  dst_ip: string;
  src_port: number;
  dst_port: number;
  protocol: number;
  duration: number;
  sbytes: number;
  dbytes: number;
  spkts: number;
  dpkts: number;
}

interface Prediction {
  class_id: number;
  class_label: string;
  probabilities: number[];
  model_version: string;
}

interface Decision {
  priority: string;
  action: string;
  p_attack: number;
}

interface FlowResult {
  type: "flow_result";
  timestamp: number;
  flow_id: string;
  flow_summary: FlowSummary;
  prediction: Prediction | null;
  decision: Decision | null;
}

interface CaptureStats {
  type: "capture_stats";
  elapsed_seconds: number;
  packets_captured: number;
  packets_dropped: number;
  active_flows: number;
  completed_flows: number;
  flows_per_second: number;
  alerts_count: Record<string, number>;
}

interface ControlMessage {
  type: "control";
  status: string;
  interface?: string;
  filter?: string;
  final_stats?: CaptureStats;
}

interface ErrorMsg {
  type: "error";
  message: string;
  available?: string[];
}

type WsMessage = FlowResult | CaptureStats | ControlMessage | ErrorMsg;

/* ================================================================== */
/*  Constants                                                          */
/* ================================================================== */

const PROTOCOL_MAP: Record<number, string> = {
  1: "ICMP",
  6: "TCP",
  17: "UDP",
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

const MAX_RESULTS = 200; // keep the last N flow results in the table

// WebSocket reconnection
const WS_RECONNECT_BASE_MS = 1000;    // initial delay
const WS_RECONNECT_MAX_MS = 30000;    // cap at 30s
const WS_MAX_RETRIES = 10;

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

function formatDuration(seconds: number): string {
  if (seconds < 0.001) return "<1ms";
  if (seconds < 1) return `${(seconds * 1000).toFixed(1)}ms`;
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs.toFixed(0)}s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function PriorityBadge({ priority }: { priority: string }) {
  const color = PRIORITY_COLORS[priority] || "#6b7280";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "#fff",
        backgroundColor: color,
        textTransform: "uppercase",
      }}
    >
      {priority}
    </span>
  );
}

/* ================================================================== */
/*  LiveCapture Component                                              */
/* ================================================================== */

export default function LiveCapture() {
  // ── Interface selection ──
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);
  const [selectedIf, setSelectedIf] = useState("");
  const [bpfFilter, setBpfFilter] = useState("");
  const [loadingIfs, setLoadingIfs] = useState(false);

  // ── Npcap / libpcap status ──
  const [pcapAvailable, setPcapAvailable] = useState<boolean | null>(null);
  const [pcapHint, setPcapHint] = useState<string | null>(null);

  // ── Capture state ──
  const [capturing, setCapturing] = useState(false);
  const [paused, setPaused] = useState(false);
  const [stats, setStats] = useState<CaptureStats | null>(null);
  const [results, setResults] = useState<FlowResult[]>([]);
  const [error, setError] = useState("");

  // ── WebSocket ──
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stoppingRef = useRef(false); // prevents reconnect on intentional close
  const capturingRef = useRef(false); // mirror of capturing state for closures
  const reconnectAttemptRef = useRef(0); // exponential backoff counter

  // ── Reconnect visual state ──
  const [reconnecting, setReconnecting] = useState(false);

  // ── Filter state ──
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const tableEndRef = useRef<HTMLDivElement>(null);

  // Keep capturingRef in sync with state (avoids stale closures)
  useEffect(() => {
    capturingRef.current = capturing;
  }, [capturing]);

  // ────────────────────────────────────────────
  //  Load interfaces on mount
  // ────────────────────────────────────────────
  useEffect(() => {
    // Check pcap availability on mount
    fetchPcapStatus()
      .then((status) => {
        setPcapAvailable(status.available);
        if (!status.available) {
          setPcapHint(status.hint);
        }
      })
      .catch(() => {
        // If the endpoint isn't available, assume pcap is fine
        // (older backend without the check-pcap endpoint)
        setPcapAvailable(true);
      });

    loadInterfaces();
    return () => {
      // Cleanup WebSocket on unmount
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
    };
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && tableEndRef.current) {
      tableEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [results, autoScroll]);

  const loadInterfaces = async () => {
    setLoadingIfs(true);
    setError("");
    try {
      const data = await fetchCaptureInterfaces();
      setInterfaces(data.interfaces || []);
      if (data.interfaces.length > 0 && !selectedIf) {
        // Default to first "up" interface, or first overall
        const up = data.interfaces.find((i) => i.is_up);
        setSelectedIf((up || data.interfaces[0]).name);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load interfaces");
    } finally {
      setLoadingIfs(false);
    }
  };

  // ────────────────────────────────────────────
  //  WebSocket management
  // ────────────────────────────────────────────
  const connectWs = useCallback(() => {
    // Guard: prevent duplicate connections (OPEN or still CONNECTING)
    const existing = wsRef.current;
    if (
      existing &&
      (existing.readyState === WebSocket.OPEN ||
        existing.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    // Clear any pending reconnect
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }

    // Close any lingering socket in CLOSING state
    if (existing) {
      try { existing.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }

    const ws = new WebSocket(`${getWsBase()}/ws/live`);
    wsRef.current = ws;

    ws.onopen = () => {
      setError("");
      setReconnecting(false);
      reconnectAttemptRef.current = 0; // reset on successful connect
      // Send start command
      ws.send(
        JSON.stringify({
          action: "start",
          interface: selectedIf,
          filter: bpfFilter,
        })
      );
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);

        switch (msg.type) {
          case "flow_result":
            setResults((prev) => {
              const next = [...prev, msg as FlowResult];
              return next.length > MAX_RESULTS
                ? next.slice(next.length - MAX_RESULTS)
                : next;
            });
            break;

          case "capture_stats":
            setStats(msg as CaptureStats);
            break;

          case "control":
            handleControlMsg(msg as ControlMessage);
            break;

          case "error":
            setError((msg as ErrorMsg).message);
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!stoppingRef.current && capturingRef.current) {
        const attempt = reconnectAttemptRef.current;
        if (attempt >= WS_MAX_RETRIES) {
          setError(
            `Connection lost after ${WS_MAX_RETRIES} reconnection attempts. ` +
            `Click Stop and try again.`
          );
          setReconnecting(false);
          return;
        }
        // Exponential backoff: 1s, 2s, 4s, 8s, … capped at 30s
        const delay = Math.min(
          WS_RECONNECT_BASE_MS * Math.pow(2, attempt),
          WS_RECONNECT_MAX_MS,
        );
        reconnectAttemptRef.current = attempt + 1;
        setReconnecting(true);
        reconnectTimer.current = setTimeout(connectWs, delay);
      }
    };

    ws.onerror = () => {
      // Only show error if not already reconnecting (avoid duplicate messages)
      if (!reconnecting) {
        setError("WebSocket connection failed");
      }
    };
  }, [selectedIf, bpfFilter]);

  const handleControlMsg = (msg: ControlMessage) => {
    switch (msg.status) {
      case "started":
        setCapturing(true);
        setPaused(false);
        break;
      case "stopped":
        setCapturing(false);
        setPaused(false);
        setStats(null);
        break;
      case "paused":
        setPaused(true);
        break;
      case "resumed":
        setPaused(false);
        break;
    }
  };

  const sendWsAction = (action: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action }));
    }
  };

  // ────────────────────────────────────────────
  //  Control handlers
  // ────────────────────────────────────────────
  const handleStart = () => {
    if (!selectedIf) {
      setError("Select a network interface first");
      return;
    }
    setError("");
    setResults([]);
    setStats(null);
    setCapturing(true); // set immediately to prevent double-click
    connectWs();
  };

  const handleStop = () => {
    stoppingRef.current = true; // prevent onclose from reconnecting
    sendWsAction("stop");
    setCapturing(false);
    setPaused(false);
    setStats(null); // clear stats so the UI resets to idle state
    setReconnecting(false);
    reconnectAttemptRef.current = 0;
    // Give the server a moment to process the stop before closing
    setTimeout(() => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      stoppingRef.current = false;
    }, 500);
  };

  const handlePause = () => sendWsAction("pause");
  const handleResume = () => sendWsAction("resume");

  // ────────────────────────────────────────────
  //  Filtered results
  // ────────────────────────────────────────────
  const filteredResults =
    priorityFilter === "all"
      ? results
      : results.filter(
          (r) =>
            r.decision?.priority?.toLowerCase() === priorityFilter
        );

  // Alert counts from stats
  const alertCounts = stats?.alerts_count || {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };

  // ────────────────────────────────────────────
  //  Render
  // ────────────────────────────────────────────
  return (
    <div style={{ padding: "24px", maxWidth: "1400px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "16px" }}>
        Live Packet Capture
      </h1>

      {error && <ErrorMessage message={error} />}

      {/* ── Npcap / libpcap missing warning ── */}
      {pcapAvailable === false && (
        <div
          style={{
            padding: "16px",
            marginBottom: "16px",
            borderRadius: "8px",
            backgroundColor: "#fef2f2",
            border: "1px solid #fca5a5",
            color: "#991b1b",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: "6px", fontSize: "0.95rem" }}>
            ⚠ Packet Capture Library Not Found
          </div>
          <p style={{ margin: 0, fontSize: "0.85rem", lineHeight: 1.5 }}>
            {pcapHint || (
              "Install Npcap from https://npcap.com/#download — during installation, " +
              "check \"Install Npcap in WinPcap API-compatible mode\". " +
              "Then restart the SentinelAI backend."
            )}
          </p>
        </div>
      )}

      {/* ── Control Panel ── */}
      <div
        style={{
          display: "flex",
          gap: "12px",
          alignItems: "flex-end",
          flexWrap: "wrap",
          marginBottom: "20px",
          padding: "16px",
          border: "1px solid #e5e7eb",
          borderRadius: "8px",
          backgroundColor: "#f9fafb",
        }}
      >
        {/* Interface selector */}
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "#374151" }}>
            Network Interface
          </label>
          <div style={{ display: "flex", gap: "4px" }}>
            <select
              value={selectedIf}
              onChange={(e) => setSelectedIf(e.target.value)}
              disabled={capturing}
              style={{
                padding: "6px 10px",
                borderRadius: "4px",
                border: "1px solid #d1d5db",
                fontSize: "0.875rem",
                minWidth: "200px",
              }}
            >
              <option value="">— Select interface —</option>
              {interfaces.map((iface) => (
                <option key={iface.name} value={iface.name}>
                  {iface.name}
                  {iface.addresses.length > 0 ? ` (${iface.addresses[0]})` : ""}
                  {!iface.is_up ? " [DOWN]" : ""}
                </option>
              ))}
            </select>
            <button
              onClick={loadInterfaces}
              disabled={capturing || loadingIfs}
              style={{
                padding: "6px 10px",
                borderRadius: "4px",
                border: "1px solid #d1d5db",
                backgroundColor: "#fff",
                cursor: "pointer",
                fontSize: "0.875rem",
              }}
              title="Refresh interfaces"
            >
              {loadingIfs ? "..." : "↻"}
            </button>
          </div>
        </div>

        {/* BPF Filter */}
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "#374151" }}>
            BPF Filter (optional)
          </label>
          <input
            type="text"
            value={bpfFilter}
            onChange={(e) => setBpfFilter(e.target.value)}
            disabled={capturing}
            placeholder="e.g. tcp port 80"
            style={{
              padding: "6px 10px",
              borderRadius: "4px",
              border: "1px solid #d1d5db",
              fontSize: "0.875rem",
              width: "200px",
            }}
          />
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: "8px" }}>
          {!capturing && !stats ? (
            <button
              onClick={handleStart}
              disabled={!selectedIf || pcapAvailable === false}
              style={{
                padding: "8px 20px",
                borderRadius: "6px",
                border: "none",
                backgroundColor: (selectedIf && pcapAvailable !== false) ? "#22c55e" : "#9ca3af",
                color: "#fff",
                fontWeight: 600,
                cursor: (selectedIf && pcapAvailable !== false) ? "pointer" : "not-allowed",
                fontSize: "0.875rem",
              }}
            >
              ▶ Start Capture
            </button>
          ) : (
            <>
              {paused ? (
                <button
                  onClick={handleResume}
                  style={{
                    padding: "8px 20px",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: "#3b82f6",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: "0.875rem",
                  }}
                >
                  ▶ Resume
                </button>
              ) : (
                <button
                  onClick={handlePause}
                  style={{
                    padding: "8px 20px",
                    borderRadius: "6px",
                    border: "none",
                    backgroundColor: "#eab308",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: "0.875rem",
                  }}
                >
                  ⏸ Pause
                </button>
              )}
              <button
                onClick={handleStop}
                style={{
                  padding: "8px 20px",
                  borderRadius: "6px",
                  border: "none",
                  backgroundColor: "#ef4444",
                  color: "#fff",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: "0.875rem",
                }}
              >
                ⏹ Stop
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Reconnecting banner ── */}
      {reconnecting && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 16px",
            marginBottom: "12px",
            borderRadius: "8px",
            backgroundColor: "#fef9c3",
            border: "1px solid #facc15",
            fontSize: "0.85rem",
            color: "#854d0e",
          }}
        >
          <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>
          Reconnecting to server… (attempt {reconnectAttemptRef.current} of {WS_MAX_RETRIES})
        </div>
      )}

      {/* ── Stats Dashboard ── */}
      {(capturing || stats) && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "12px",
            marginBottom: "20px",
          }}
        >
          <StatCard
            label="Elapsed"
            value={stats ? formatElapsed(stats.elapsed_seconds) : "0s"}
          />
          <StatCard
            label="Packets"
            value={stats?.packets_captured?.toLocaleString() || "0"}
          />
          <StatCard
            label="Active Flows"
            value={stats?.active_flows?.toLocaleString() || "0"}
          />
          <StatCard
            label="Completed"
            value={stats?.completed_flows?.toLocaleString() || "0"}
          />
          <StatCard
            label="Flows/sec"
            value={stats?.flows_per_second?.toFixed(1) || "0.0"}
          />
          <StatCard
            label="Critical"
            value={String(alertCounts.critical || 0)}
            color="#ef4444"
          />
          <StatCard
            label="High"
            value={String(alertCounts.high || 0)}
            color="#f97316"
          />
          <StatCard
            label="Medium"
            value={String(alertCounts.medium || 0)}
            color="#eab308"
          />
        </div>
      )}

      {/* ── Filter bar ── */}
      {results.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "12px",
            alignItems: "center",
            marginBottom: "12px",
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#374151" }}>
            Filter:
          </span>
          {["all", "critical", "high", "medium", "low"].map((p) => (
            <button
              key={p}
              onClick={() => setPriorityFilter(p)}
              style={{
                padding: "4px 12px",
                borderRadius: "12px",
                border:
                  priorityFilter === p
                    ? "2px solid #3b82f6"
                    : "1px solid #d1d5db",
                backgroundColor:
                  priorityFilter === p ? "#eff6ff" : "#fff",
                fontSize: "0.75rem",
                fontWeight: priorityFilter === p ? 600 : 400,
                cursor: "pointer",
                textTransform: "capitalize",
              }}
            >
              {p} {p !== "all" ? `(${results.filter((r) => r.decision?.priority === p).length})` : `(${results.length})`}
            </button>
          ))}

          <label
            style={{
              marginLeft: "auto",
              fontSize: "0.75rem",
              color: "#6b7280",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
        </div>
      )}

      {/* ── Results Table ── */}
      {results.length > 0 && (
        <div
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            overflow: "auto",
            maxHeight: "500px",
          }}
        >
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.8rem",
            }}
          >
            <thead>
              <tr
                style={{
                  backgroundColor: "#f3f4f6",
                  position: "sticky",
                  top: 0,
                  zIndex: 1,
                }}
              >
                <th style={thStyle}>Priority</th>
                <th style={thStyle}>Source</th>
                <th style={thStyle}>Destination</th>
                <th style={thStyle}>Proto</th>
                <th style={thStyle}>Duration</th>
                <th style={thStyle}>Pkts</th>
                <th style={thStyle}>Bytes</th>
                <th style={thStyle}>Classification</th>
                <th style={thStyle}>p(Attack)</th>
                <th style={thStyle}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredResults.map((r, idx) => (
                <tr
                  key={`${r.flow_id}-${idx}`}
                  style={{
                    borderBottom: "1px solid #f3f4f6",
                    backgroundColor:
                      r.decision?.priority === "critical"
                        ? "#fef2f2"
                        : r.decision?.priority === "high"
                        ? "#fff7ed"
                        : undefined,
                  }}
                >
                  <td style={tdStyle}>
                    <PriorityBadge
                      priority={r.decision?.priority || "low"}
                    />
                  </td>
                  <td style={tdStyle}>
                    {r.flow_summary.src_ip}:{r.flow_summary.src_port}
                  </td>
                  <td style={tdStyle}>
                    {r.flow_summary.dst_ip}:{r.flow_summary.dst_port}
                  </td>
                  <td style={tdStyle}>
                    {PROTOCOL_MAP[r.flow_summary.protocol] ||
                      r.flow_summary.protocol}
                  </td>
                  <td style={tdStyle}>
                    {formatDuration(r.flow_summary.duration)}
                  </td>
                  <td style={tdStyle}>
                    {r.flow_summary.spkts + r.flow_summary.dpkts}
                  </td>
                  <td style={tdStyle}>
                    {formatBytes(
                      r.flow_summary.sbytes + r.flow_summary.dbytes
                    )}
                  </td>
                  <td style={tdStyle}>
                    {r.prediction?.class_label || "—"}
                  </td>
                  <td style={tdStyle}>
                    {r.decision
                      ? `${(r.decision.p_attack * 100).toFixed(1)}%`
                      : "—"}
                  </td>
                  <td style={tdStyle}>
                    <span
                      style={{
                        textTransform: "capitalize",
                        fontWeight:
                          r.decision?.action === "escalate" ? 600 : 400,
                      }}
                    >
                      {r.decision?.action || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div ref={tableEndRef} />
        </div>
      )}

      {/* ── Empty state ── */}
      {(capturing || stats) && results.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#6b7280",
          }}
        >
          <LoadingSpinner />
          <p style={{ marginTop: "12px" }}>
            Waiting for flows to complete...
          </p>
          <p style={{ fontSize: "0.75rem" }}>
            Flows complete on TCP FIN/RST or after the idle timeout
            (30s default).
          </p>
        </div>
      )}

      {!capturing && !stats && results.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#6b7280",
            border: "1px dashed #d1d5db",
            borderRadius: "8px",
          }}
        >
          <p style={{ fontSize: "1.1rem", marginBottom: "8px" }}>
            Select a network interface and click Start Capture
          </p>
          <p style={{ fontSize: "0.75rem" }}>
            Live flows will appear here with real-time ML classification and triage.
          </p>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Sub-components                                                     */
/* ================================================================== */

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div
      style={{
        padding: "12px 16px",
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
        backgroundColor: "#fff",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: "0.7rem",
          fontWeight: 600,
          color: "#6b7280",
          textTransform: "uppercase",
          marginBottom: "4px",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.25rem",
          fontWeight: 700,
          color: color || "#111827",
        }}
      >
        {value}
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Style helpers                                                      */
/* ================================================================== */

const thStyle: React.CSSProperties = {
  padding: "8px 10px",
  textAlign: "left",
  fontWeight: 600,
  fontSize: "0.75rem",
  color: "#374151",
  borderBottom: "2px solid #e5e7eb",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "6px 10px",
  whiteSpace: "nowrap",
};