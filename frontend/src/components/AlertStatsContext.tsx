import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  ReactNode,
} from "react";
import { getAlerts } from "../api";

/* ================================================================== */
/*  Types                                                              */
/* ================================================================== */

export interface AlertRecord {
  id?: number;
  timestamp: string;
  class_id: number;
  class_label?: string;
  probabilities?: Record<string, number> | number[];
  priority?: string;
  predicted_score?: number;
  recommended_action?: string;
  decision?: {
    predicted_class?: string;
    priority?: string;
    recommended_action?: string;
    decision_confidence?: number;
    decision_status?: string;
    evidence?: string[];
    uncertainty_reasons?: string[];
    requires_human_review?: boolean;
    policy_mode?: string;
  };
  policy_mode?: string;
  /** Source of this alert: "triage", "live", or "batch" */
  source?: "triage" | "live" | "batch";
  /** Analyst workflow status */
  alert_status?: "new" | "acknowledged" | "investigating" | "resolved" | "false_positive";
}

interface AlertStatsContextValue {
  /** All alerts (persistent DB + session, all sources) */
  alerts: AlertRecord[];
  /** Current browser session alerts only */
  sessionAlerts: AlertRecord[];
  /** Live capture session alerts */
  liveAlerts: AlertRecord[];
  /** Batch upload session alerts */
  batchAlerts: AlertRecord[];
  /** Add an alert with source tag */
  addAlert: (alert: AlertRecord) => void;
  /** Add multiple alerts at once (batch/live results) */
  addAlerts: (alerts: AlertRecord[]) => void;
  /** Update alert status (analyst workflow) */
  updateAlertStatus: (alertKey: string, status: AlertRecord["alert_status"]) => void;
  /** Clear session alerts */
  clear: () => void;
  /** Refresh from backend DB */
  refresh: () => Promise<void>;
}

const AlertStatsContext = createContext<AlertStatsContextValue | null>(null);

/* ================================================================== */
/*  Provider                                                           */
/* ================================================================== */

export function AlertStatsProvider({ children }: { children: ReactNode }) {
  const [dbAlerts, setDbAlerts] = useState<AlertRecord[]>([]);
  const [sessionAlerts, setSessionAlerts] = useState<AlertRecord[]>([]);

  const refresh = useCallback(async () => {
    try {
      const data = await getAlerts(500);
      const records: AlertRecord[] = (data as any[]).map((r: any) => ({
        ...r,
        source: r.source || "triage",
      }));
      setDbAlerts(records);
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addAlert = useCallback((alert: AlertRecord) => {
    const tagged = { ...alert, source: alert.source || "triage" } as AlertRecord;
    setSessionAlerts((prev) => {
      const key = tagged.id
        ? `id-${tagged.id}`
        : `${tagged.timestamp}-${tagged.class_id}`;
      const exists = prev.some((p) => {
        const pk = p.id ? `id-${p.id}` : `${p.timestamp}-${p.class_id}`;
        return pk === key;
      });
      return exists ? prev : [...prev, tagged];
    });
  }, []);

  const addAlerts = useCallback((newAlerts: AlertRecord[]) => {
    setSessionAlerts((prev) => {
      const existingKeys = new Set(
        prev.map((p) =>
          p.id ? `id-${p.id}` : `${p.timestamp}-${p.class_id}`
        )
      );
      const unique = newAlerts
        .map((a) => ({ ...a, source: a.source || "triage" } as AlertRecord))
        .filter((a) => {
          const k = a.id ? `id-${a.id}` : `${a.timestamp}-${a.class_id}`;
          if (existingKeys.has(k)) return false;
          existingKeys.add(k);
          return true;
        });
      return [...prev, ...unique];
    });
  }, []);

  const updateAlertStatus = useCallback(
    (alertKey: string, status: AlertRecord["alert_status"]) => {
      // Update in session alerts
      setSessionAlerts((prev) =>
        prev.map((a) => {
          const k = a.id ? `id-${a.id}` : `${a.timestamp}-${a.class_id}`;
          return k === alertKey ? { ...a, alert_status: status } : a;
        })
      );
      // Update in DB alerts
      setDbAlerts((prev) =>
        prev.map((a) => {
          const k = a.id ? `id-${a.id}` : `${a.timestamp}-${a.class_id}`;
          return k === alertKey ? { ...a, alert_status: status } : a;
        })
      );
      // Persist to backend if it has an id
      const idMatch = alertKey.match(/^id-(\d+)$/);
      if (idMatch) {
        fetch(`/api/alerts/${idMatch[1]}/status`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ alert_status: status }),
        }).catch(() => {/* silent — local state is source of truth for session */ });
      }
    },
    []
  );

  const clear = useCallback(() => {
    setSessionAlerts([]);
  }, []);

  /* Merge DB + session, dedup */
  const alerts = (() => {
    const seen = new Set<string>();
    const merged: AlertRecord[] = [];
    for (const a of [...dbAlerts, ...sessionAlerts]) {
      const k = a.id ? `id-${a.id}` : `${a.timestamp}-${a.class_id}`;
      if (!seen.has(k)) {
        seen.add(k);
        merged.push(a);
      }
    }
    return merged;
  })();

  const liveAlerts = sessionAlerts.filter((a) => a.source === "live");
  const batchAlerts = sessionAlerts.filter((a) => a.source === "batch");

  return (
    <AlertStatsContext.Provider
      value={{
        alerts,
        sessionAlerts,
        liveAlerts,
        batchAlerts,
        addAlert,
        addAlerts,
        updateAlertStatus,
        clear,
        refresh,
      }}
    >
      {children}
    </AlertStatsContext.Provider>
  );
}

export function useAlertStats() {
  const ctx = useContext(AlertStatsContext);
  if (!ctx) throw new Error("useAlertStats must be inside AlertStatsProvider");
  return ctx;
}

export default AlertStatsContext;