import React from 'react';

/**
 * ShapTopFeatures Component
 *
 * Props:
 *   explanations – either a dictionary {featureName: shapValue} or an array [{name, value}]
 *   title – optional title for the widget
 */
export default function ShapTopFeatures({
  explanations = {},
  title = "Top SHAP Features",
}: {
  explanations?: Record<string, number> | { name: string; value: number }[];
  title?: string;
}) {
  // Normalise the input to a list of {name, value}
  let features: { name: string; value: number }[] = [];
  if (Array.isArray(explanations)) {
    features = explanations as any;
  } else if (explanations && typeof explanations === "object") {
    features = Object.entries(explanations as Record<string, number>).map(([name, value]) => ({
      name,
      value,
    }));
  }

  if (features.length === 0) {
    return (
      <div className="p-4 bg-white shadow rounded-lg border border-gray-200 text-gray-500">
        No SHAP data available.
      </div>
    );
  }

  // Keep only the top 5 by absolute magnitude
  const topFeatures = features
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 5);

  const maxAbs = Math.max(...topFeatures.map(f => Math.abs(f.value)), 0.001);

  return (
    <div className="p-6 bg-white shadow-md rounded-xl border border-gray-100 max-w-md w-full">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">{title}</h3>
      <div className="space-y-3">
        {topFeatures.map((f, i) => {
          const positive = f.value >= 0;
          const barWidth = `${(Math.abs(f.value) / maxAbs) * 100}%`;
          return (
            <div key={i} className="flex flex-col text-sm">
              <div className="flex justify-between mb-1">
                <span className="font-medium text-gray-700 truncate max-w-[200px]" title={f.name}>
                  {f.name}
                </span>
                <span className={`font-mono text-xs ${positive ? "text-red-600" : "text-blue-600"}`}>
                  {positive ? `+${f.value.toFixed(3)}` : f.value.toFixed(3)}
                </span>
              </div>
              <div style={{
        width: '100%',
        backgroundColor: '#e5e7eb', // Tailwind bg-gray-100 equivalent
        height: '10px',
        borderRadius: '5px',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
      }}>
  <div style={{
        height: '100%',
        width: barWidth,
        backgroundColor: positive ? '#ef4444' : '#3b82f6', // red-500 / blue-500
        transition: 'width 0.3s',
      }} />
</div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-100 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Higher prediction</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Lower prediction</span>
      </div>
    </div>
  );
}
