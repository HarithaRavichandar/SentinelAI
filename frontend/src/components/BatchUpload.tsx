import { useState, useRef, useCallback, useEffect } from "react";
import { uploadBatchCSV, pollBatchStatus, fetchBatchResults } from "../api";
import LoadingSpinner from "./LoadingSpinner";
import ErrorMessage from "./ErrorMessage";
import { useAlertStats, AlertRecord } from "./AlertStatsContext";

/* ================================================================== */
/*  Types                                                              */
/* ================================================================== */

interface PredictionObject {
  class_id: number;
  class_label: string;
  probabilities: Record<string, number> | number[];
  model_version: string;
}

interface DecisionObject {
  predicted_class: string;
  priority: string;
  recommended_action: string;
  decision_confidence: number;
  decision_status: string;
  evidence: string[];
  uncertainty_reasons: string[];
  requires_human_review: boolean;
  policy_mode: string;
}

interface RawBatchResult {
  row?: number;
  features?: Record<string, number>;
  prediction: string | PredictionObject;
  confidence?: number;
  decision?: string | DecisionObject;
}

interface BatchResult {
  row: number;
  label: string;
  confidence: number;
  decision: {
    priority: string;
    action: string;
    escalate: boolean;
  };
}

interface JobState {
  job_id: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  results: BatchResult[];
  errors: string[];
}

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

const MAX_FILE_SIZE_MB = 10;
const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 200; // ~5 min timeout

function isFinished(status: string) {
  const s = status.toLowerCase();
  return s === "done" || s === "completed";
}

function normalizeResult(r: RawBatchResult, index: number): BatchResult {
  let label: string;
  let confidence: number;
  let priority = "medium";
  let action = "";
  let escalate = false;

  /* --- prediction & probabilities --- */
  if (typeof r.prediction === "object" && r.prediction !== null) {
    const pred = r.prediction as PredictionObject;
    label = pred.class_label ?? ("Class " + pred.class_id);

    if (Array.isArray(pred.probabilities) && pred.probabilities.length > 0) {
      confidence = Math.max(...pred.probabilities);
    } else if (
      typeof pred.probabilities === "object" &&
      pred.probabilities !== null
    ) {
      const vals = Object.values(pred.probabilities).filter(
        (v): v is number => typeof v === "number"
      );
      confidence = vals.length > 0 ? Math.max(...vals) : 0;
    } else {
      confidence = typeof r.confidence === "number" ? r.confidence : 0;
    }
  } else {
    label = String(r.prediction);
    confidence = typeof r.confidence === "number" ? r.confidence : 0;
  }

  /* --- decision object --- */
  if (typeof r.decision === "object" && r.decision !== null) {
    const dec = r.decision as DecisionObject;
    if (typeof dec.decision_confidence === "number") {
      confidence = dec.decision_confidence;
    }
    priority = dec.priority ?? priority;
    action = dec.recommended_action ?? "";
    escalate = dec.requires_human_review ?? false;
  } else if (typeof r.decision === "string") {
    action = r.decision;
  }

  const row = typeof r.row === "number" ? r.row : index + 1;

  return { row, label, confidence, decision: { priority, action, escalate } };
}

const priorityColor: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

const priorityOrder: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function formatAction(raw: string): string {
  if (!raw) return "—";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function exportResultsCSV(results: BatchResult[], jobId: string) {
  const header =
    "Row,Prediction,Confidence,Priority,Action,Requires Review\n";
  const rows = results
    .map(
      (r) =>
        `${r.row},"${r.label}",${(r.confidence * 100).toFixed(2)}%,"${r.decision.priority}","${formatAction(r.decision.action)}",${r.decision.escalate}`
    )
    .join("\n");
  const blob = new Blob([header + rows], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sentinelai_batch_${jobId.slice(0, 8)}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ================================================================== */
/*  Component                                                          */
/* ================================================================== */

export default function BatchUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [job, setJob] = useState<JobState | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<
    "row" | "label" | "confidence" | "priority"
  >("row");
  const [sortAsc, setSortAsc] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  const { addAlerts } = useAlertStats();

  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  /* cleanup on unmount */
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  /* ── file validation ── */
  const validateFile = (f: File): string | null => {
    if (!f.name.toLowerCase().endsWith(".csv")) {
      return "Only .csv files are accepted.";
    }
    const sizeMB = f.size / (1024 * 1024);
    if (sizeMB > MAX_FILE_SIZE_MB) {
      return `File too large (${sizeMB.toFixed(1)} MB). Maximum is ${MAX_FILE_SIZE_MB} MB.`;
    }
    if (f.size === 0) {
      return "File is empty.";
    }
    return null;
  };

  /* ── drag-and-drop handlers ── */
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);
  const onDragLeave = useCallback(() => setDragOver(false), []);
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (!dropped) return;
    const err = validateFile(dropped);
    if (err) {
      setError(err);
    } else {
      setFile(dropped);
      setError(null);
    }
  }, []);

  /* ── file picker ── */
  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    if (!f) return;
    const err = validateFile(f);
    if (err) {
      setError(err);
      return;
    }
    setFile(f);
    setError(null);
  };

  /* ── upload + poll ── */
  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setJob(null);
    setElapsed(0);
    pollCountRef.current = 0;

    try {
      const res = await uploadBatchCSV(file);
      if (res.errors && res.errors.length > 0) {
        setError(res.errors.join("\n"));
        setUploading(false);
        return;
      }

      const jobId = res.job_id;
      setJob({
        job_id: jobId,
        status: "queued",
        total_rows: 0,
        processed_rows: 0,
        results: [],
        errors: [],
      });
      setUploading(false);

      /* start elapsed timer */
      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);

      /* start polling */
      pollRef.current = setInterval(async () => {
        pollCountRef.current += 1;

        /* timeout guard */
        if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
          if (pollRef.current) clearInterval(pollRef.current);
          if (timerRef.current) clearInterval(timerRef.current);
          setError(
            "Processing timed out. The job may still be running on the server — try refreshing."
          );
          return;
        }

        try {
          const st = await pollBatchStatus(jobId);
          setJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: st.status,
                  total_rows: st.total_rows,
                  processed_rows: st.processed_rows,
                }
              : prev
          );

          if (isFinished(st.status) || st.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current);
            if (timerRef.current) clearInterval(timerRef.current);

            try {
              const final_res = await fetchBatchResults(jobId);
              const normalized = (final_res.results ?? []).map(
                (raw: any, idx: number) =>
                  normalizeResult(raw as RawBatchResult, idx)
              );
              setJob((prev) =>
                prev
                  ? {
                      ...prev,
                      status: final_res.status ?? st.status,
                      results: normalized,
                      errors: final_res.errors ?? [],
                    }
                  : prev
              );

              // Feed into unified Dashboard via AlertStatsContext
              if (normalized.length > 0) {
                const batchAlerts: AlertRecord[] = normalized.map(
                  (r: BatchResult, idx: number) => ({
                    timestamp: new Date().toISOString(),
                    class_id: idx,
                    class_label: r.label,
                    priority: r.decision?.priority || "medium",
                    predicted_score: r.confidence,
                    recommended_action: r.decision?.action,
                    source: "batch" as const,
                  })
                );
                addAlerts(batchAlerts);
              }
            } catch (_) {
              setError("Job completed but failed to fetch results.");
            }
          }
        } catch (_) {
          /* tolerate up to 3 consecutive poll failures before giving up */
          if (pollCountRef.current > 3) {
            if (pollRef.current) clearInterval(pollRef.current);
            if (timerRef.current) clearInterval(timerRef.current);
            setError("Lost connection while polling job status.");
          }
        }
      }, POLL_INTERVAL_MS);
    } catch (err: unknown) {
      setUploading(false);
      const msg =
        err instanceof Error ? err.message : "Upload failed.";
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        setError(
          "Cannot reach the backend server. Make sure it is running on http://127.0.0.1:8000"
        );
      } else {
        setError(msg);
      }
    }
  };

  /* ── reset ── */
  const handleReset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    setFile(null);
    setJob(null);
    setError(null);
    setElapsed(0);
    setSortField("row");
    setSortAsc(true);
    if (fileRef.current) fileRef.current.value = "";
  };

  /* ── sorting ── */
  const handleSort = (field: typeof sortField) => {
    if (field === sortField) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortedResults = job?.results
    ? [...job.results].sort((a, b) => {
        let cmp = 0;
        switch (sortField) {
          case "row":
            cmp = a.row - b.row;
            break;
          case "label":
            cmp = a.label.localeCompare(b.label);
            break;
          case "confidence":
            cmp = a.confidence - b.confidence;
            break;
          case "priority":
            cmp =
              (priorityOrder[a.decision.priority?.toLowerCase()] ?? 9) -
              (priorityOrder[b.decision.priority?.toLowerCase()] ?? 9);
            break;
        }
        return sortAsc ? cmp : -cmp;
      })
    : [];

  /* ── computed stats ── */
  const results = job?.results ?? [];
  const benignCount = results.filter(
    (r) => r.label.toLowerCase() === "benign"
  ).length;
  const attackCount = results.length - benignCount;
  const reviewCount = results.filter((r) => r.decision.escalate).length;
  const avgConfidence =
    results.length > 0
      ? results.reduce((s, r) => s + r.confidence, 0) / results.length
      : 0;

  /* ── progress ── */
  const pct =
    job && job.total_rows > 0
      ? Math.round((job.processed_rows / job.total_rows) * 100)
      : 0;

  const fmtElapsed = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;

  /* sort indicator */
  const sortArrow = (field: typeof sortField) =>
    sortField === field ? (sortAsc ? " ▲" : " ▼") : "";

  /* ================================================================ */
  /*  Render                                                           */
  /* ================================================================ */
  return (
    <div style={{ padding: "2rem", maxWidth: 1100, margin: "0 auto" }}>
      {/* header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h2
          style={{
            margin: 0,
            fontSize: "1.5rem",
            color: "#e2e8f0",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          Batch Upload
          <span
            style={{
              fontSize: "0.7rem",
              background: "#0ea5e9",
              color: "#fff",
              padding: "2px 8px",
              borderRadius: 4,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            CSV Ingestion
          </span>
        </h2>
        <p style={{ color: "#94a3b8", marginTop: 4, fontSize: "0.85rem" }}>
          Upload a CSV file with 76 UNSW-NB15 features to classify network flows
          in batch. Results include predictions, confidence scores, and
          deterministic triage decisions.
        </p>
      </div>

      {/* ── drop zone ── */}
      {!job && (
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? "#0ea5e9" : "#334155"}`,
            borderRadius: 12,
            padding: "3rem 2rem",
            textAlign: "center",
            cursor: "pointer",
            background: dragOver ? "rgba(14,165,233,0.06)" : "#0f172a",
            transition: "all 0.2s",
            marginBottom: "1rem",
          }}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            onChange={onFileChange}
            style={{ display: "none" }}
          />
          <div style={{ fontSize: "2.5rem", marginBottom: 8 }}>📁</div>
          <p style={{ color: "#cbd5e1", margin: 0, fontWeight: 500 }}>
            {file
              ? file.name
              : "Drag & drop a CSV file here, or click to browse"}
          </p>
          {file && (
            <p style={{ color: "#64748b", fontSize: "0.8rem", marginTop: 4 }}>
              {(file.size / 1024).toFixed(1)} KB
            </p>
          )}
          <p
            style={{
              color: "#475569",
              fontSize: "0.75rem",
              marginTop: 8,
            }}
          >
            Max {MAX_FILE_SIZE_MB} MB · CSV format · 76 feature columns
          </p>
        </div>
      )}

      {/* ── action buttons ── */}
      {!job && (
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            style={{
              padding: "0.6rem 1.5rem",
              borderRadius: 8,
              border: "none",
              background:
                !file || uploading
                  ? "#1e293b"
                  : "linear-gradient(135deg, #0ea5e9, #6366f1)",
              color: !file || uploading ? "#475569" : "#fff",
              fontWeight: 600,
              cursor: !file || uploading ? "not-allowed" : "pointer",
              fontSize: "0.9rem",
            }}
          >
            {uploading ? "Uploading…" : "Upload & Process"}
          </button>
          {file && (
            <button
              onClick={handleReset}
              style={{
                padding: "0.6rem 1.2rem",
                borderRadius: 8,
                border: "1px solid #334155",
                background: "transparent",
                color: "#94a3b8",
                cursor: "pointer",
                fontSize: "0.9rem",
              }}
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* ── error ── */}
      {error && (
        <div style={{ marginTop: "1rem" }}>
          <ErrorMessage message={error} />
        </div>
      )}

      {/* ── uploading spinner ── */}
      {uploading && (
        <div style={{ marginTop: "2rem" }}>
          <LoadingSpinner />
        </div>
      )}

      {/* ── progress bar ── */}
      {job && !isFinished(job.status) && job.status !== "error" && (
        <div
          style={{
            marginTop: "1.5rem",
            background: "#0f172a",
            borderRadius: 12,
            padding: "1.5rem",
            border: "1px solid #1e293b",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >
            <span style={{ color: "#cbd5e1", fontWeight: 500 }}>
              Processing batch…
            </span>
            <span style={{ color: "#0ea5e9", fontWeight: 600 }}>
              {job.processed_rows} / {job.total_rows} rows ({pct}%)
            </span>
          </div>
          <div
            style={{
              height: 8,
              borderRadius: 4,
              background: "#1e293b",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${pct}%`,
                background: "linear-gradient(90deg, #0ea5e9, #6366f1)",
                borderRadius: 4,
                transition: "width 0.4s ease",
              }}
            />
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: 8,
            }}
          >
            <p
              style={{
                color: "#64748b",
                fontSize: "0.8rem",
                margin: 0,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              Status: {job.status}
            </p>
            <p
              style={{
                color: "#64748b",
                fontSize: "0.8rem",
                margin: 0,
              }}
            >
              Elapsed: {fmtElapsed}
            </p>
          </div>
        </div>
      )}

      {/* ── results ── */}
      {job && isFinished(job.status) && results.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          {/* completed banner */}
          <div
            style={{
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.3)",
              borderRadius: 8,
              padding: "0.6rem 1rem",
              marginBottom: "1rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ color: "#22c55e", fontWeight: 500, fontSize: "0.85rem" }}>
              ✓ Batch completed — {results.length} flow{results.length !== 1 ? "s" : ""} classified
            </span>
            <span style={{ color: "#64748b", fontSize: "0.8rem" }}>
              {fmtElapsed} elapsed
            </span>
          </div>

          {/* summary cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "1rem",
              marginBottom: "1.5rem",
            }}
          >
            <SummaryCard label="Total Rows" value={results.length} color="#0ea5e9" />
            <SummaryCard label="Benign" value={benignCount} color="#22c55e" />
            <SummaryCard label="Attack" value={attackCount} color="#f97316" />
            <SummaryCard label="Needs Review" value={reviewCount} color="#ef4444" />
            <SummaryCard
              label="Avg Confidence"
              value={`${(avgConfidence * 100).toFixed(1)}%`}
              color="#a78bfa"
            />
          </div>

          {/* table header + actions */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "1rem",
            }}
          >
            <h3 style={{ margin: 0, color: "#e2e8f0", fontSize: "1.1rem" }}>
              Classification Results
            </h3>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <button
                onClick={() => exportResultsCSV(results, job.job_id)}
                style={{
                  padding: "0.4rem 1rem",
                  borderRadius: 6,
                  border: "1px solid #334155",
                  background: "#1e293b",
                  color: "#cbd5e1",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  fontWeight: 500,
                }}
              >
                ⬇ Export CSV
              </button>
              <button
                onClick={handleReset}
                style={{
                  padding: "0.4rem 1rem",
                  borderRadius: 6,
                  border: "1px solid #334155",
                  background: "transparent",
                  color: "#94a3b8",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                }}
              >
                New Batch
              </button>
            </div>
          </div>

          {/* results table */}
          <div
            style={{
              overflowX: "auto",
              borderRadius: 10,
              border: "1px solid #1e293b",
            }}
          >
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.85rem",
              }}
            >
              <thead>
                <tr
                  style={{
                    background: "#0f172a",
                    textAlign: "left",
                    color: "#94a3b8",
                    textTransform: "uppercase",
                    fontSize: "0.75rem",
                    letterSpacing: "0.06em",
                  }}
                >
                  <SortTh
                    label="Row"
                    field="row"
                    current={sortField}
                    asc={sortAsc}
                    onClick={handleSort}
                  />
                  <SortTh
                    label="Prediction"
                    field="label"
                    current={sortField}
                    asc={sortAsc}
                    onClick={handleSort}
                  />
                  <SortTh
                    label="Confidence"
                    field="confidence"
                    current={sortField}
                    asc={sortAsc}
                    onClick={handleSort}
                  />
                  <SortTh
                    label="Priority"
                    field="priority"
                    current={sortField}
                    asc={sortAsc}
                    onClick={handleSort}
                  />
                  <th style={{ padding: "0.75rem 1rem" }}>Action</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Review</th>
                </tr>
              </thead>
              <tbody>
                {sortedResults.map((r, i) => (
                  <tr
                    key={r.row}
                    style={{
                      background: i % 2 === 0 ? "#0b1120" : "#0f172a",
                      borderTop: "1px solid #1e293b",
                    }}
                  >
                    <td style={{ padding: "0.6rem 1rem", color: "#64748b" }}>
                      {r.row}
                    </td>
                    <td
                      style={{
                        padding: "0.6rem 1rem",
                        fontWeight: 500,
                        color:
                          r.label.toLowerCase() === "benign"
                            ? "#4ade80"
                            : "#fb923c",
                      }}
                    >
                      {r.label}
                    </td>
                    <td style={{ padding: "0.6rem 1rem", color: "#cbd5e1" }}>
                      {(r.confidence * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: "0.6rem 1rem" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 10px",
                          borderRadius: 4,
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          color: "#fff",
                          background:
                            priorityColor[
                              r.decision.priority?.toLowerCase()
                            ] ?? "#475569",
                          textTransform: "uppercase",
                        }}
                      >
                        {r.decision.priority}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 1rem", color: "#cbd5e1" }}>
                      {formatAction(r.decision.action)}
                    </td>
                    <td style={{ padding: "0.6rem 1rem" }}>
                      {r.decision.escalate ? (
                        <span style={{ color: "#ef4444", fontWeight: 600 }}>
                          ⚠ YES
                        </span>
                      ) : (
                        <span style={{ color: "#22c55e" }}>No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* errors if any */}
          {job.errors.length > 0 && (
            <div
              style={{
                marginTop: "1rem",
                background: "#1c1917",
                borderRadius: 8,
                padding: "1rem",
                border: "1px solid #7f1d1d",
              }}
            >
              <h4 style={{ color: "#ef4444", margin: "0 0 0.5rem" }}>
                Processing Errors ({job.errors.length})
              </h4>
              {job.errors.map((e, i) => (
                <p
                  key={i}
                  style={{
                    color: "#fca5a5",
                    fontSize: "0.8rem",
                    margin: "2px 0",
                  }}
                >
                  • {e}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── completed with zero results ── */}
      {job && isFinished(job.status) && results.length === 0 && (
        <div
          style={{
            marginTop: "1.5rem",
            background: "#0f172a",
            borderRadius: 12,
            padding: "2rem",
            textAlign: "center",
            border: "1px solid #1e293b",
          }}
        >
          <p style={{ color: "#94a3b8", fontSize: "1rem", margin: 0 }}>
            No results returned. The CSV may have no valid rows, or all rows
            produced errors.
          </p>
          {job.errors.length > 0 && (
            <div style={{ marginTop: "1rem", textAlign: "left" }}>
              {job.errors.map((e, i) => (
                <p
                  key={i}
                  style={{
                    color: "#fca5a5",
                    fontSize: "0.8rem",
                    margin: "2px 0",
                  }}
                >
                  • {e}
                </p>
              ))}
            </div>
          )}
          <button
            onClick={handleReset}
            style={{
              marginTop: "1rem",
              padding: "0.5rem 1.2rem",
              borderRadius: 8,
              border: "1px solid #334155",
              background: "transparent",
              color: "#94a3b8",
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      )}

      {/* ── error state from job ── */}
      {job && job.status === "error" && (
        <div style={{ marginTop: "1.5rem" }}>
          <ErrorMessage message="Batch processing failed. Check backend logs." />
          <button
            onClick={handleReset}
            style={{
              marginTop: "1rem",
              padding: "0.5rem 1.2rem",
              borderRadius: 8,
              border: "1px solid #334155",
              background: "transparent",
              color: "#94a3b8",
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  Sub-components                                                     */
/* ================================================================== */

function SortTh({
  label,
  field,
  current,
  asc,
  onClick,
}: {
  label: string;
  field: "row" | "label" | "confidence" | "priority";
  current: string;
  asc: boolean;
  onClick: (f: "row" | "label" | "confidence" | "priority") => void;
}) {
  return (
    <th
      style={{
        padding: "0.75rem 1rem",
        cursor: "pointer",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
      onClick={() => onClick(field)}
    >
      {label}
      {current === field ? (asc ? " ▲" : " ▼") : ""}
    </th>
  );
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div
      style={{
        background: "#0f172a",
        borderRadius: 10,
        padding: "1rem 1.25rem",
        border: "1px solid #1e293b",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.75rem",
          color: "#64748b",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontWeight: 600,
        }}
      >
        {label}
      </p>
      <p
        style={{
          margin: "4px 0 0",
          fontSize: "1.5rem",
          fontWeight: 700,
          color,
        }}
      >
        {value}
      </p>
    </div>
  );
}