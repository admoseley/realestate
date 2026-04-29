function Bar({ label, value, max, color }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-gray-600">{label}</span>
        <span className="font-medium text-brand-charcoal">{value}</span>
      </div>
      <div className="h-2 bg-brand-line rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%`, transition: "width 0.5s ease" }} />
      </div>
    </div>
  );
}

export default function NeighborhoodPanel({ deal }) {
  const nb = deal.neighborhood || {};
  if (!nb.school_rating && !nb.crime_index) return null;

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold text-brand-charcoal">Neighborhood</h4>

      {nb.school_district && (
        <p className="text-xs text-gray-500">
          School District: <span className="font-medium text-brand-charcoal">{nb.school_district}</span>
          {nb.school_grade && <span className="ml-2 px-1.5 py-0.5 bg-brand-tint text-brand-dark rounded text-xs">{nb.school_grade}</span>}
        </p>
      )}

      {nb.school_rating != null && (
        <Bar label="School Rating" value={nb.school_rating.toFixed(1)} max={10} color="bg-brand-sky" />
      )}

      {nb.crime_index != null && (
        <Bar label="Crime Index (lower=safer)" value={nb.crime_index} max={100} color="bg-red-400" />
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        {nb.violent_per_1k != null && (
          <div className="bg-white rounded p-2 border border-brand-line">
            <p className="text-gray-500">Violent / 1k</p>
            <p className="font-bold text-brand-charcoal">{nb.violent_per_1k.toFixed(1)}</p>
          </div>
        )}
        {nb.property_per_1k != null && (
          <div className="bg-white rounded p-2 border border-brand-line">
            <p className="text-gray-500">Property / 1k</p>
            <p className="font-bold text-brand-charcoal">{nb.property_per_1k.toFixed(1)}</p>
          </div>
        )}
        {nb.crime_grade && (
          <div className="bg-white rounded p-2 border border-brand-line col-span-2">
            <p className="text-gray-500">Crime Grade</p>
            <p className="font-bold text-brand-charcoal">{nb.crime_grade}</p>
          </div>
        )}
      </div>
    </div>
  );
}
