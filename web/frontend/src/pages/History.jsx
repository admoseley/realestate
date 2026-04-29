import { useEffect, useState, useCallback } from "react";
import { listReports, getReport, deleteReport, pdfUrl } from "../api/client";
import PropertyCard from "../components/PropertyCard";
import VerdictBadge from "../components/VerdictBadge";

const PAGE_SIZE = 10;

export default function History() {
  const [reports,  setReports]  = useState([]);
  const [page,     setPage]     = useState(0);
  const [expanded, setExpanded] = useState(null);
  const [detail,   setDetail]   = useState({});
  const [loading,  setLoading]  = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    listReports(page * PAGE_SIZE, PAGE_SIZE)
      .then(setReports)
      .finally(() => setLoading(false));
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    if (!detail[id]) {
      const r = await getReport(id);
      setDetail(d => ({ ...d, [id]: r }));
    }
  };

  const del = async (id, e) => {
    e.stopPropagation();
    if (!confirm("Delete this report and its PDF?")) return;
    await deleteReport(id);
    setReports(rs => rs.filter(r => r.id !== id));
    if (expanded === id) setExpanded(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-charcoal">Report History</h1>
        <p className="text-sm text-gray-500 mt-1">All past analyses — click a row to expand deal cards</p>
      </div>

      {loading && <p className="text-gray-400 text-sm">Loading…</p>}

      {!loading && reports.length === 0 && (
        <div className="bg-white rounded-xl border border-brand-line p-12 text-center text-gray-400">
          No reports yet. Run a Sheriff Sale analysis or Spot Check to get started.
        </div>
      )}

      {reports.length > 0 && (
        <div className="bg-white rounded-xl border border-brand-line overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brand-gray border-b border-brand-line text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-2 text-left">Date</th>
                  <th className="px-4 py-2 text-left">Type</th>
                  <th className="px-4 py-2 text-left">Title</th>
                  <th className="px-4 py-2 text-center">Props</th>
                  <th className="px-4 py-2 text-center">BUY</th>
                  <th className="px-4 py-2 text-center">PERFECT</th>
                  <th className="px-4 py-2 text-center">PDF</th>
                  <th className="px-4 py-2 text-center">Del</th>
                </tr>
              </thead>
              <tbody>
                {reports.map(r => (
                  <>
                    <tr
                      key={r.id}
                      className="border-t border-brand-line hover:bg-brand-gray/50 cursor-pointer"
                      onClick={() => toggle(r.id)}
                    >
                      <td className="px-4 py-2 text-gray-500 whitespace-nowrap">
                        {new Date(r.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          r.type === "sheriff_sale"
                            ? "bg-brand-tint text-brand-dark"
                            : "bg-blue-50 text-blue-700"
                        }`}>
                          {r.type === "sheriff_sale" ? "Sheriff Sale" : "Spot Check"}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-brand-charcoal font-medium max-w-xs truncate">{r.title}</td>
                      <td className="px-4 py-2 text-center">{r.property_count}</td>
                      <td className="px-4 py-2 text-center font-bold text-verdict-buy">{r.buy_count}</td>
                      <td className="px-4 py-2 text-center font-bold text-brand-orange">{r.perfect_count}</td>
                      <td className="px-4 py-2 text-center" onClick={e => e.stopPropagation()}>
                        {r.has_pdf && (
                          <a href={pdfUrl(r.id)} target="_blank" rel="noreferrer"
                            className="text-brand-orange hover:underline font-semibold text-xs">
                            ↓ PDF
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <button onClick={(e) => del(r.id, e)}
                          className="text-red-400 hover:text-red-600 text-xs font-semibold">
                          ✕
                        </button>
                      </td>
                    </tr>

                    {expanded === r.id && detail[r.id] && (
                      <tr key={`exp-${r.id}`} className="border-t border-brand-line bg-brand-gray/20">
                        <td colSpan={8} className="p-4">
                          <div className="space-y-4">
                            {detail[r.id].deals.map((d, i) => (
                              <PropertyCard key={i} deal={d} rank={i + 1} />
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="px-4 py-3 border-t border-brand-line flex items-center justify-between">
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
              className="text-sm text-brand-orange font-semibold disabled:opacity-30 hover:underline">
              ← Prev
            </button>
            <span className="text-xs text-gray-500">Page {page + 1}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={reports.length < PAGE_SIZE}
              className="text-sm text-brand-orange font-semibold disabled:opacity-30 hover:underline">
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
