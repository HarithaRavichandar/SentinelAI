import React, { useState } from 'react';
import { postTriage, getSample } from '../api';
import { useAlertStats } from './AlertStatsContext';
import LoadingSpinner from './LoadingSpinner';
import ErrorMessage from './ErrorMessage';
import ShapTopFeatures from './ShapTopFeatures';

// Load the demo fixture at runtime from Vite public directory
const loadSampleFeatures = async () => {
  const resp = await fetch(import.meta.env.BASE_URL + 'sample_features.json');
  if (!resp.ok) throw new Error('Unable to load sample features');
  return await resp.json();
};

function TriageView() {
  const { addAlert } = useAlertStats();
  const [payload, setPayload] = useState<string>('');
  const [explainShap, setExplainShap] = useState<boolean>(false);
  const [sampleLabel, setSampleLabel] = useState<string>(''); // known label from dataset sample
  const [selectedClass, setSelectedClass] = useState<string>(''); // specific class for sample loading

  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load fixture on component mount (fallback sample)
  React.useEffect(() => {
    loadSampleFeatures()
      .then((data) => setPayload(JSON.stringify(data, null, 2)))
      .catch((e) => setError(e.message));
  }, []);

  // Load a real dataset sample on demand
  const loadRealSample = async (targetClass?: string) => {
    const classToUse = typeof targetClass === 'string' ? targetClass : selectedClass;
    setLoading(true);
    setError(null);
    setResult(null); // Clear previous prediction results when a new sample is loaded
    try {
      const resp = await getSample(classToUse || undefined);
      setPayload(JSON.stringify(resp.features, null, 2));
      setSampleLabel(resp.label ?? '');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClassChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const nextClass = e.target.value;
    setSelectedClass(nextClass);
    loadRealSample(nextClass);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    let parsed;
    try {
      parsed = JSON.parse(payload);
    } catch (err) {
      setError('Invalid JSON payload');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Request triage, optionally with SHAP explanations based on user selection
      const start = performance.now();
      const res = await postTriage(parsed, explainShap);
      const latency = performance.now() - start;
      setResult(res);
      addAlert({
        id: res.id,
        timestamp: Date.now(),
        class_id: res.class_id,
        class_label: res.class_label,
        probabilities: res.probabilities,
        latencyMs: Math.round(latency),
        // Preserve actual triage decision metadata from backend
        priority: res.decision?.priority,
        decision_status: res.decision?.decision_status,
        recommended_action: res.decision?.recommended_action,
        decision_confidence: res.decision?.decision_confidence,
        requires_human_review: res.decision?.requires_human_review,
        policy_mode: res.decision?.policy_mode,
        decision: res.decision,
      });
    } catch (err: any) {
      // Handle network/HTTP errors and display message
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="triage-page">
      <h1 className="text-2xl mb-2">Alert Triage</h1>
      <p className="mb-4 text-sm text-gray-400">Edit the JSON payload and run the model for classification.</p>
      <div className="card p-4">
        <form onSubmit={handleSubmit}>
          <textarea
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            className="triage-editor"
          />
          <div className="triage-toolbar">
            <label>
              <input
                type="checkbox"
                id="shapCheckbox"
                checked={explainShap}
                onChange={(e) => setExplainShap(e.target.checked)}
              />
              <span className="text-sm">Include SHAP explanations</span>
            </label>
            <select
              value={selectedClass}
              onChange={handleClassChange}
              disabled={loading}
              className="bg-[#1e1e1e] border border-[#424242] text-gray-200 px-2 py-1.5 rounded text-sm"
              title="Select sample class"
            >
              <option value="">Any Class (Random)</option>
              <option value="Benign">Benign</option>
              <option value="Analysis">Analysis</option>
              <option value="Backdoor">Backdoor</option>
              <option value="DoS">DoS</option>
              <option value="Exploits">Exploits</option>
              <option value="Fuzzers">Fuzzers</option>
              <option value="Generic">Generic</option>
              <option value="Reconnaissance">Reconnaissance</option>
              <option value="Shellcode">Shellcode</option>
              <option value="Worms">Worms</option>
            </select>
            <button type="button" onClick={() => loadRealSample(selectedClass)} disabled={loading}>
              Load Real Sample
            </button>
            <button type="submit" disabled={loading}>Run Triage</button>
          </div>
        </form>
      </div>
      {loading && <LoadingSpinner />}
      {error && <ErrorMessage message={error} />}
      {sampleLabel && (
        <p className="mt-2 text-sm"><strong>Dataset label (offline sample):</strong> {sampleLabel}</p>
      )}
      {result && (
        <div className="mt-6 card">
          <h2 className="text-xl mb-2">Result</h2>
          <p><strong>Predicted Class:</strong> {result.class_label ?? 'N/A'} (ID: {result.class_id ?? 'N/A'})</p>
          {result.probabilities && (
            <div className="mt-2">
              <p className="font-medium mb-1">Model Scores:</p>
                              <div className="score-container">
                {[ { id: 0, label: 'Benign' }, { id: 1, label: 'Analysis' }, { id: 2, label: 'Backdoor' }, { id: 3, label: 'DoS' }, { id: 4, label: 'Exploits' }, { id: 5, label: 'Fuzzers' }, { id: 6, label: 'Generic' }, { id: 7, label: 'Reconnaissance' }, { id: 8, label: 'Shellcode' }, { id: 9, label: 'Worms' }].map(({ id, label }) => { const score = result.probabilities?.[id] ?? 0; return ( <div key={id} className="score-row"> <span className="score-label">{label}</span> <div className="score-bar-bg"> <div className="score-bar-fill" style={{ width: `${(Number(score) * 100).toFixed(1)}%` }}></div> </div> <span className="score-value">{Number(score).toFixed(3)}</span> </div> ); })}


              </div>
            </div>
          )}
          {result.decision && (
            <div className="mt-4 p-4 border border-[#424242] rounded-lg bg-[#18181b]">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold text-white">Laya Triage Decision</h3>
                <div className="flex items-center space-x-2">
                  <span className={`px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                    result.decision.priority === 'critical' ? 'bg-red-900/60 text-red-300 border border-red-700' :
                    result.decision.priority === 'high' ? 'bg-orange-900/60 text-orange-300 border border-orange-700' :
                    result.decision.priority === 'medium' ? 'bg-yellow-900/60 text-yellow-300 border border-yellow-700' :
                    result.decision.priority === 'low' ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700' :
                    'bg-zinc-800 text-zinc-300 border border-zinc-600'
                  }`}>
                    Priority: {result.decision.priority}
                  </span>
                  <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-zinc-800 text-zinc-300 border border-zinc-700">
                    Status: {result.decision.decision_status}
                  </span>
                  {result.decision.policy_mode ? (
                    <span className={`px-2.5 py-0.5 rounded text-xs font-medium ${
                      result.decision.policy_mode === 'two_stage_experimental'
                        ? 'bg-purple-950/80 text-purple-300 border border-purple-800'
                        : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                    }`} title={result.decision.policy_mode === 'two_stage_experimental' ? 'Evaluated by experimental two-stage triage policy' : 'Evaluated by legacy deterministic decision engine'}>
                      Policy: {result.decision.policy_mode === 'two_stage_experimental' ? 'Two-Stage (Exp)' : 'Legacy'}
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded text-xs font-mono text-zinc-400 border border-zinc-700" title="Policy provenance not recorded">
                      Policy: Unknown
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3 text-sm">
                <div>
                  <span className="text-gray-400">Recommended Action (Advisory):</span>{' '}
                  <code className="text-cyan-300 font-mono bg-zinc-900 px-1.5 py-0.5 rounded text-xs">
                    {result.decision.recommended_action}
                  </code>
                </div>
                <div>
                  <span className="text-gray-400">Decision Confidence (Heuristic):</span>{' '}
                  <span className="font-semibold text-white">
                    {(Number(result.decision.decision_confidence || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {result.decision.requires_human_review && (
                <div className="mb-3 px-3 py-2 rounded text-xs bg-amber-950/50 border border-amber-800/80 text-amber-200 flex items-center gap-2">
                  <span className="font-bold">⚠️ Human Review Required:</span>
                  <span>Operational response requires analyst validation before automated enforcement.</span>
                </div>
              )}

              {result.decision.evidence?.length > 0 && (
                <div className="mt-2 text-xs">
                  <span className="font-semibold text-gray-300">Supporting Evidence:</span>
                  <ul className="list-disc pl-4 mt-1 text-gray-400 space-y-0.5">
                    {result.decision.evidence.map((ev: string, idx: number) => (
                      <li key={idx}>{ev}</li>
                    ))}
                  </ul>
                </div>
              )}

              {result.decision.uncertainty_reasons?.length > 0 && (
                <div className="mt-2 text-xs">
                  <span className="font-semibold text-amber-400">Uncertainty Drivers:</span>
                  <ul className="list-disc pl-4 mt-1 text-amber-300/90 space-y-0.5">
                    {result.decision.uncertainty_reasons.map((ur: string, idx: number) => (
                      <li key={idx}>{ur}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="mt-3 pt-2 border-t border-[#333] text-[11px] text-gray-400">
                <strong>Advisory Guardrail:</strong> Decision confidence is a heuristic score, not a calibrated statistical probability.{' '}
                {result.decision.decision_status === 'review_required' ? (
                  <>
                    Status &lsquo;review_required&rsquo; indicates the advisory assessment exhibits ambiguity or elevated uncertainty; human analyst review is required before any operational response. It does not confirm an attack or execute automated enforcement actions.{' '}
                  </>
                ) : result.decision.decision_status === 'accepted' ? (
                  <>
                    Status &lsquo;accepted&rsquo; indicates the advisory assessment meets routing confidence criteria; it does not confirm an attack or execute operational changes.{' '}
                  </>
                ) : (
                  <>
                    Status &lsquo;{result.decision.decision_status || 'unknown'}&rsquo; indicates the advisory assessment requires manual analyst inspection before any operational response. It does not confirm an attack or execute automated enforcement actions.{' '}
                  </>
                )}
                All actions are advisory only.
              </p>
            </div>
          )}

          {/* Explanation summary */}
          <div className="mt-2">
            <p className="font-medium mb-1">Explanation Summary:</p>
            <p>Predicted class: {result.class_label ?? 'N/A'} (ID: {result.class_id ?? 'N/A'}).</p>
            <p>Highest model score: {(() => {
              const entries = Object.entries(result.probabilities ?? {});
              if (entries.length === 0) return 'N/A';
              const [maxId, maxScore] = entries.reduce((a, b) => (Number(b[1]) > Number(a[1]) ? b : a));
              const labels = ['Benign','Analysis','Backdoor','DoS','Exploits','Fuzzers','Generic','Reconnaissance','Shellcode','Worms'];
              const label = labels[Number(maxId)] ?? maxId;
              return `${label} (${Number(maxScore).toFixed(3)})`;
            })()}.</p>
            <p>Model scores are not calibrated probabilities and do not prove an attack.</p>
          </div>
          {result.explanation && (
            <div className="mt-4 p-4 border border-[#424242] rounded-lg bg-[#18181b]">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-white">
                  {result.explanation_provenance?.is_llm || result.explanation_source === 'groq' || result.explanation_source === 'gemini'
                    ? 'AI Explanation'
                    : 'Explanation'}
                </span>
                {(() => {
                  const src = result.explanation_provenance?.source || result.explanation_source;
                  if (src === 'groq') {
                    return (
                      <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800">
                        Generated by Groq
                      </span>
                    );
                  }
                  if (src === 'gemini') {
                    return (
                      <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-blue-950/80 text-blue-300 border border-blue-800">
                        Generated by Gemini
                      </span>
                    );
                  }
                  if (src === 'template' || src === 'placeholder') {
                    return (
                      <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
                        Template explanation
                      </span>
                    );
                  }
                  return null;
                })()}
              </div>
              <p className="whitespace-pre-wrap break-words text-sm text-gray-300">
                {result.explanation?.replace(/\*\*/g, '')}
              </p>
            </div>
          )}
          {result.shap_explanations && (
          <div className="mt-2">
            <h2 className="text-xl mb-2">SHAP Feature Contributions</h2>
            {/* Explain direction */}
            <p className="text-sm mb-2">
              Positive values increase the model's output for the predicted class, negative values decrease it. These are not labels such as “malicious” or “benign”.
            </p>
            <ShapTopFeatures explanations={result.shap_explanations} />
            {/* Collapsible raw SHAP JSON */}
            <details className="mt-4">
              <summary>Show raw SHAP values</summary>
              <pre className="whitespace-pre-wrap bg-gray-100 p-2 rounded mt-2">
                {JSON.stringify(result.shap_explanations, null, 2)}
              </pre>
            </details>
          </div>
        )}


          {result.shap_status && (
            <div className="mt-2">
              <p className="font-medium mb-1">SHAP Status:</p>
              <p>{result.shap_status}</p>
            </div>
          )}
          <p className="mt-2 text-sm"><strong>Note:</strong> Model scores are not calibrated probabilities and do not prove an attack.</p>
          <details className="mt-4">
            <summary>Show raw API response</summary>
            <pre className="whitespace-pre-wrap bg-gray-100 p-2 rounded mt-2">{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default TriageView;
