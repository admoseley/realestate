const fmt  = (v) => v != null ? `$${Number(v).toLocaleString(undefined, {maximumFractionDigits:0})}` : "—";
const fmtP = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

function Pass({ pass }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${pass ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
      {pass ? "PASS" : "FAIL"}
    </span>
  );
}

export default function RentalTable({ deal }) {
  const rows = [
    ["Market Rent",       fmt(deal.market_rent)],
    ["Gross Rent (EGI)",  fmt(deal.egi)],
    ["Op. Expenses",      fmt(deal.op_expenses)],
    ["NOI / Month",       fmt(deal.monthly_noi)],
    ["NOI / Year",        fmt(deal.annual_noi)],
    ["Cap Rate",          fmtP(deal.cap_rate)],
    ["DSCR",              deal.dscr?.toFixed(2) ?? "—"],
    ["1% Rule",           deal.one_pct_rule != null ? `${deal.one_pct_rule.toFixed(2)}%` : "—"],
    ["Cash-on-Cash",      fmtP(deal.cash_on_cash)],
    ["Payback",           deal.payback_months != null ? `${deal.payback_months} mo` : "—"],
  ];

  const stressTests = deal.stress_tests?.rental || [];

  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold text-brand-charcoal">Rental / Hold Analysis</h4>
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
          <h4 className="text-sm font-semibold text-brand-charcoal pt-2">Rental Stress Tests</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-brand-gray">
                <th className="py-1 px-2 text-left text-gray-500 font-medium">Scenario</th>
                <th className="py-1 px-2 text-right text-gray-500 font-medium">NOI/mo</th>
                <th className="py-1 px-2 text-right text-gray-500 font-medium">Cap</th>
                <th className="py-1 px-2 text-center text-gray-500 font-medium">Pass</th>
              </tr>
            </thead>
            <tbody>
              {stressTests.map((st, i) => (
                <tr key={i} className="border-b border-brand-line">
                  <td className="py-1 px-2 text-gray-600">{st.label}</td>
                  <td className="py-1 px-2 text-right font-medium">{fmt(st.noi_monthly)}</td>
                  <td className="py-1 px-2 text-right">{fmtP(st.cap_rate)}</td>
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
