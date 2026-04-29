const fmt  = (v, prefix="$") => v != null ? `${prefix}${Number(v).toLocaleString(undefined, {maximumFractionDigits: 0})}` : "—";
const fmtP = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

export default function MetricGrid({ deal }) {
  const tiles = [
    { label: "Min Bid",     value: fmt(deal.min_bid) },
    { label: "FMV",         value: fmt(deal.fmv) },
    { label: "ARV",         value: fmt(deal.arv) },
    { label: "Flip Profit", value: fmt(deal.flip_net_profit), highlight: deal.flip_net_profit > 0 },
    { label: "Cap Rate",    value: fmtP(deal.cap_rate) },
    { label: "DSCR",        value: deal.dscr != null ? Number(deal.dscr).toFixed(2) : "—" },
    { label: "Mo. NOI",     value: fmt(deal.monthly_noi) },
    { label: "Payback",     value: deal.payback_months != null ? `${deal.payback_months}mo` : "—" },
  ];

  return (
    <div className="grid grid-cols-4 gap-2">
      {tiles.map(({ label, value, highlight }) => (
        <div key={label} className={`rounded-lg p-3 text-center border ${highlight ? "bg-emerald-50 border-emerald-200" : "bg-white border-brand-line"}`}>
          <p className="text-xs text-gray-500 mb-1">{label}</p>
          <p className={`text-base font-bold ${highlight ? "text-emerald-700" : "text-brand-charcoal"}`}>{value}</p>
        </div>
      ))}
    </div>
  );
}
