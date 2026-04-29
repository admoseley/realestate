const fmt = (v) => v != null ? `$${Number(v).toLocaleString(undefined, {maximumFractionDigits:0})}` : "—";
const fmtP = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

function Pass({ pass }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${pass ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
      {pass ? "PASS" : "FAIL"}
    </span>
  );
}

export default function FlipTable({ deal }) {
  const rows = [
    ["Purchase Price",   fmt(deal.min_bid)],
    ["Rehab Est.",       fmt(deal.rehab_cost)],
    ["Holding Costs",    fmt(deal.holding_costs)],
    ["Closing Costs",    fmt(deal.closing_costs)],
    ["All-In Cost",      fmt(deal.all_in_cost)],
    ["ARV",              fmt(deal.arv)],
    ["Net Proceeds",     fmt(deal.flip_net_proceeds)],
    ["Flip Profit",      fmt(deal.flip_net_profit)],
    ["ROI",              fmtP(deal.flip_roi)],
    ["IRR (12mo)",       fmtP(deal.flip_irr)],
    ["MAO",              fmt(deal.mao)],
    ["70% Rule MAO",     fmt(deal.rule70_mao)],
  ];

  const stressTests = deal.stress_tests?.flip || [];

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold text-brand-charcoal">Flip Analysis</h4>
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([label, val]) => (
            <tr key={label} className="border-b border-brand-line">
              <td className="py-1 text-gray-500 w-1/2">{label}</td>
              <td className="py-1 font-medium text-brand-charcoal text-right">{val}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {stressTests.length > 0 && (
        <>
          <h4 className="text-sm font-semibold text-brand-charcoal pt-2">Flip Stress Tests</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-brand-gray">
                <th className="py-1 px-2 text-left text-gray-500 font-medium">Scenario</th>
                <th className="py-1 px-2 text-right text-gray-500 font-medium">Profit</th>
                <th className="py-1 px-2 text-right text-gray-500 font-medium">ROI</th>
                <th className="py-1 px-2 text-center text-gray-500 font-medium">Pass</th>
              </tr>
            </thead>
            <tbody>
              {stressTests.map((st, i) => (
                <tr key={i} className="border-b border-brand-line">
                  <td className="py-1 px-2 text-gray-600">{st.label}</td>
                  <td className="py-1 px-2 text-right font-medium">{fmt(st.profit)}</td>
                  <td className="py-1 px-2 text-right">{fmtP(st.roi)}</td>
                  <td className="py-1 px-2 text-center"><Pass pass={st.pass} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
