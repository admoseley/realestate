export default function RedFlagList({ deal }) {
  const flags = deal.red_flags || [];
  if (flags.length === 0) {
    return (
      <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 text-sm">
        <span>✓</span>
        <span>No critical flags detected</span>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <h4 className="text-sm font-semibold text-brand-charcoal mb-2">Red Flags</h4>
      {flags.map((flag, i) => (
        <div key={i} className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-100 rounded px-3 py-1.5">
          <span className="mt-0.5 flex-shrink-0">⚠</span>
          <span>{flag}</span>
        </div>
      ))}
    </div>
  );
}
