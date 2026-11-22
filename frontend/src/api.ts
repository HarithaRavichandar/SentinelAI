// src/api.ts
/**
 * Simple API wrapper that reads the base URL from the environment variable
 * `VITE_API_BASE`. During development this defaults to `http://127.0.0.1:8000`.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";


export async function getHealth() {
  const resp = await fetch(`${API_BASE}/health`);
  if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
  return resp.json();
}

export async function postPredict(payload: Record<string, unknown>) {
  const resp = await fetch(`${API_BASE}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail ?? `Predict failed: ${resp.status}`);
  }
  return resp.json();
}


export async function postTriage(
  payload: Record<string, unknown>,
  explainShap = false
) {
  const url = new URL(`${API_BASE}/triage`);

  if (explainShap) {
    url.searchParams.set("explain_shap", "true");
  }

  console.log("POST URL:", url.toString());

  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail ?? `Triage failed: ${resp.status}`);
  }

  return resp.json();
}


export async function postDecision(
  payload: Record<string, unknown>,
  explainShap = false
) {
  const url = new URL(`${API_BASE}/decision`);

  if (explainShap) {
    url.searchParams.set("explain_shap", "true");
  }

  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail ?? `Decision failed: ${resp.status}`);
  }

  return resp.json();
}


export async function postChat(message: string, history?: any[]) {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_history: history ?? null }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail ?? `Chat failed: ${resp.status}`);
  }
  return resp.json();
};

export async function getSample(label?: string) {
  const url = new URL(`${API_BASE}/sample`, typeof window !== "undefined" ? window.location.href : undefined);
  if (label && label.trim()) {
    url.searchParams.set("label", label.trim());
  }
  const resp = await fetch(url.toString());
  if (!resp.ok) {
    const err = await resp.json().catch(() => null);
    throw new Error(err?.detail ?? `Sample fetch failed: ${resp.status}`);
  }
  return resp.json();
}

export async function getAlerts(limit = 50) {
  const resp = await fetch(`${API_BASE}/alerts?limit=${limit}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => null);
    throw new Error(err?.detail ?? `Alerts fetch failed: ${resp.status}`);
  }
  return resp.json();
}

// ─── Batch Upload API functions ───

export async function uploadBatchCSV(
  file: File
): Promise<{ job_id: string; status: string; errors: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/batch/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function pollBatchStatus(
  jobId: string
): Promise<{
  job_id: string;
  status: string;
  total_rows: number;
  processed_rows: number;
}> {
  const res = await fetch(`${API_BASE}/batch/${jobId}/status`);
  if (!res.ok) throw new Error(`Status poll failed (${res.status})`);
  return res.json();
}

export async function fetchBatchResults(
  jobId: string
): Promise<{
  job_id: string;
  status: string;
  total_rows: number;
  results: Array<{
    row: number;
    prediction: string;
    confidence: number;
    decision: { priority: string; action: string; escalate: boolean };
  }>;
  errors: string[];
}> {
  const res = await fetch(`${API_BASE}/batch/${jobId}/results`);
  if (!res.ok) throw new Error(`Results fetch failed (${res.status})`);
  return res.json();
}
// ─── Live Capture API functions ───

// ─── Live Capture API functions ───
// Add these to your frontend/src/api.ts file.
// They use the existing API_BASE constant already defined at the top of api.ts.
// DO NOT paste the API_BASE line — it already exists.

/**
 * Derive the WebSocket URL from API_BASE.
 * If API_BASE is "http://localhost:8000" → "ws://localhost:8000"
 */
export function getWsBase(): string {
  return API_BASE.replace(/^http/, "ws");
}

/**
 * Fetch available network interfaces for live capture.
 */
export async function fetchCaptureInterfaces(): Promise<{
  interfaces: Array<{
    name: string;
    addresses: string[];
    is_up: boolean;
  }>;
  error?: string;
  hint?: string;
}> {
  const res = await fetch(`${API_BASE}/capture/interfaces`);
  if (!res.ok) throw new Error(`Failed to fetch interfaces (${res.status})`);
  return res.json();
}

/**
 * Check whether Npcap (Windows) or libpcap (Linux/macOS) is available.
 * Call on mount to show a user-friendly error before the user tries to capture.
 */
export async function fetchPcapStatus(): Promise<{
  available: boolean;
  backend: string;
  message: string;
  hint: string | null;
}> {
  const res = await fetch(`${API_BASE}/capture/check-pcap`);
  if (!res.ok) throw new Error(`Failed to check pcap status (${res.status})`);
  return res.json();
}

/**
 * Fetch current capture session status.
 */
export async function fetchCaptureStatus(): Promise<{
  capturing: boolean;
  stats?: {
    elapsed_seconds: number;
    packets_captured: number;
    packets_dropped: number;
    active_flows: number;
    completed_flows: number;
    flows_per_second: number;
    alerts_count: Record<string, number>;
  };
}> {
  const res = await fetch(`${API_BASE}/capture/status`);
  if (!res.ok) throw new Error(`Failed to fetch status (${res.status})`);
  return res.json();
}