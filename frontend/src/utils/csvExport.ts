/**
 * CSV Export Utilities for SentinelAI Alert History.
 *
 * Implements RFC 4180-compliant CSV escaping, strict preservation of decision
 * metadata, omission of sensitive/raw network payloads, and date-stamped filenames.
 */

import { AlertRecord } from '../components/AlertStatsContext';

/**
 * Escapes a single CSV field in accordance with RFC 4180.
 *
 * - Null/undefined values become empty strings.
 * - Strings containing commas, quotes, carriage returns, or line breaks are
 *   enclosed in double quotes with embedded quotes escaped as double double-quotes ("").
 */
export function escapeCsvValue(val: unknown): string {
  if (val === null || val === undefined) {
    return '';
  }
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Safely extracts the predicted class score from an alert's probabilities map.
 */
export function getPredictedScore(alert: AlertRecord): number | null {
  if (!alert || !alert.probabilities || typeof alert.probabilities !== 'object') {
    return null;
  }
  const cid = alert.class_id;
  let score: unknown = undefined;

  if (cid !== undefined && cid !== null) {
    score = alert.probabilities[String(cid)] ?? (alert.probabilities as Record<number, number>)[cid];
  }

  if (score === undefined && alert.class_label) {
    const labelKey = alert.class_label;
    if (labelKey in alert.probabilities) {
      score = alert.probabilities[labelKey];
    }
  }

  if (typeof score === 'number' && Number.isFinite(score)) {
    return score;
  }
  return null;
}

export const CSV_HEADERS = [
  'alert_id',
  'timestamp',
  'timestamp_iso',
  'predicted_class',
  'class_id',
  'model_score',
  'model_scores',
  'triage_priority',
  'decision_status',
  'recommended_action',
  'decision_confidence',
  'requires_human_review',
  'policy_mode',
] as const;

/**
 * Generates RFC 4180-compliant CSV text from an array of alert records.
 *
 * Guardrail compliance:
 * - Strictly uses actual decision engine metadata (priority, status, review).
 * - Never infers or fabricates decision priority from predicted class.
 * - Missing metadata is preserved as empty fields.
 * - Never includes raw 76 network-flow feature vectors or sensitive telemetry payloads.
 */
export function generateAlertsCsv(records: AlertRecord[]): string {
  const headerLine = CSV_HEADERS.join(',');
  if (!records || records.length === 0) {
    return headerLine + '\r\n';
  }

  const rows = records.map((alert) => {
    const id = alert.id !== undefined && alert.id !== null ? alert.id : '';
    const ts = alert.timestamp;
    const tsIso = Number.isFinite(ts) ? new Date(ts).toISOString() : '';
    const predictedClass = alert.class_label || (alert.class_id !== undefined ? `Class ${alert.class_id}` : '');
    const classId = alert.class_id !== undefined && alert.class_id !== null ? alert.class_id : '';
    const scoreVal = getPredictedScore(alert);
    const modelScore = scoreVal !== null ? scoreVal.toFixed(4) : '';

    let scoresJson = '';
    if (alert.probabilities && typeof alert.probabilities === 'object') {
      try {
        scoresJson = JSON.stringify(alert.probabilities);
      } catch {
        scoresJson = '';
      }
    }

    // Actual decision-engine metadata only (never fallback threat tiers)
    const triagePriority = alert.priority || alert.decision?.priority || '';
    const decisionStatus = alert.decision_status || alert.decision?.decision_status || '';
    const recommendedAction = alert.recommended_action || alert.decision?.recommended_action || '';

    const rawConf = alert.decision_confidence ?? alert.decision?.decision_confidence;
    const decisionConfidence = rawConf !== undefined && rawConf !== null && Number.isFinite(Number(rawConf))
      ? Number(rawConf).toFixed(4)
      : '';

    const rawReview = alert.requires_human_review ?? alert.decision?.requires_human_review;
    const requiresHumanReview = rawReview !== undefined && rawReview !== null
      ? (rawReview ? 'true' : 'false')
      : '';

    const policyMode = alert.policy_mode || alert.decision?.policy_mode || '';

    return [
      escapeCsvValue(id),
      escapeCsvValue(ts),
      escapeCsvValue(tsIso),
      escapeCsvValue(predictedClass),
      escapeCsvValue(classId),
      escapeCsvValue(modelScore),
      escapeCsvValue(scoresJson),
      escapeCsvValue(triagePriority),
      escapeCsvValue(decisionStatus),
      escapeCsvValue(recommendedAction),
      escapeCsvValue(decisionConfidence),
      escapeCsvValue(requiresHumanReview),
      escapeCsvValue(policyMode),
    ].join(',');
  });

  return [headerLine, ...rows].join('\r\n') + '\r\n';
}

/**
 * Triggers a browser download of the generated CSV content with a date-stamped filename.
 */
export function downloadAlertsCsv(csvContent: string, customFilename?: string): string {
  const dateStr = new Date().toISOString().slice(0, 10);
  const filename = customFilename || `sentinelai-alerts-${dateStr}.csv`;

  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  return filename;
}

