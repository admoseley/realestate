import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listReports, pdfUrl } from "../api/client";

function StatCard({ label, value, color }) {
  return (
    <div className="bg-white rounded-xl border border-brand-line p-5 text-center">
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  );
}

function ActionCard({ title, desc, to }) {
  const nav = useNavigate();
  return (
    <button
      onClick={() => nav(to)}
      className="bg-white rounded-xl border-2 border-brand-orange p-6 text-left hover:bg-brand-tint transition-colors w-full"
    >
      <p className="text-lg font-bold text-brand-charcoal">{title}</p>
      <p className="text-sm text-gray-500 mt-1">{desc}</p>
      <span className="mt-4 inline-block bg-brand-orange text-white text-xs font-bold px-4 py-1.5 rounded-full">
        Start →
      </span>
    </button>
  );
}

export default function Dashboard() {
  const [reports, setReports] = useState([]);

  useEffect(() => {
    listReports(0, 5).then(setReports).catch(() => {});
  }, []);

  const totalProps  = reports.reduce((s, r) => s + r.property_count, 0);
  const totalBuy    = reports.reduce((s, r) => s + r.buy_count, 0);
  const totalPerfect = reports.reduce((s, r) => s + r.perfect_count, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-charcoal">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Estella Wilson Properties LLC — Investment Analysis</p>
      </div>

      {/* Action cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ActionCard
          title="Sheriff Sale Analysis"
          desc="Batch-analyze the Allegheny County sheriff sale PDF — find F&C properties ranked by score."
          to="/sheriff-sale"
        />
        <ActionCard
          title="Property Spot Check"
          desc="Enter any address + price to get a full investment analysis report on a single property."
          to="/spot-check"
        />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Reports"    value={reports.length} color="text-brand-charcoal" />
        <StatCard label="Properties Analyzed" value={totalProps} color="text-brand-charcoal" />
        <StatCard label="BUY Verdicts"     value={totalBuy}    color="text-verdict-buy" />
        <StatCard label="PERFECT Deals"    value={totalPerfect} color="text-brand-orange" />
      </div>

      {/* Recent reports */}
      {reports.length > 0 && (
        <div className="bg-white rounded-xl border border-brand-line overflow-hidden">
          <div className="px-5 py-4 border-b border-brand-line">
            <h2 className="font-semibold text-brand-charcoal">Recent Reports</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brand-gray text-gray-500 text-xs">
                <tr>
                  <th className="px-4 py-2 text-left">Date</th>
                  <th className="px-4 py-2 text-left">Title</th>
                  <th className="px-4 py-2 text-center">Props</th>
                  <th className="px-4 py-2 text-center">BUY</th>
                  <th className="px-4 py-2 text-center">PERFECT</th>
                  <th className="px-4 py-2 text-center">PDF</th>
                </tr>
              </thead>
              <tbody>
                {reports.map(r => (
                  <tr key={r.id} className="border-t border-brand-line hover:bg-brand-gray/50">
                    <td className="px-4 py-2 text-gray-500 whitespace-nowrap">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-brand-charcoal font-medium truncate max-w-xs">{r.title}</td>
                    <td className="px-4 py-2 text-center">{r.property_count}</td>
                    <td className="px-4 py-2 text-center font-bold text-verdict-buy">{r.buy_count}</td>
                    <td className="px-4 py-2 text-center font-bold text-brand-orange">{r.perfect_count}</td>
                    <td className="px-4 py-2 text-center">
                      {r.has_pdf && (
                        <a
                          href={pdfUrl(r.id)}
                          target="_blank"
                          rel="noreferrer"
                          className="text-brand-orange hover:underline font-semibold"
                        >
                          ↓ PDF
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
