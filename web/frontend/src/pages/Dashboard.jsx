import { useState, useEffect } from "react";
import { listDeals, clearDeals, updateDealAddress } from "../api/client";
import PropertyCard from "../components/PropertyCard";
import VerdictBadge from "../components/VerdictBadge";
import ShareModal from "../components/ShareModal";
import ShareFavoritesModal from "../components/ShareFavoritesModal";

const VERDICTS = ["BUY", "CONSIDER", "WATCH", "NO BUY"];

const Th = ({ col, label, sortCol, sortAsc, onSort }) => (
  <th
    className="px-3 py-2 text-left text-xs text-gray-500 font-medium cursor-pointer hover:text-brand-charcoal whitespace-nowrap"
    onClick={() => onSort(col)}
  >
    {label} {sortCol === col ? (sortAsc ? "↑" : "↓") : ""}
  </th>
);

const ThumbUp = ({ active }) => (
  <svg viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" />
    <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
  </svg>
);

const ThumbDown = ({ active }) => (
  <svg viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z" />
    <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
  </svg>
);

export default function Dashboard() {
  const [deals,       setDeals]       = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [filter,      setFilter]      = useState("ALL");
  const [sortCol,     setSortCol]     = useState("score");
  const [sortAsc,     setSortAsc]     = useState(false);
  const [expanded,    setExpanded]    = useState(null);
  const [hideLand,    setHideLand]    = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [shareTarget,        setShareTarget]        = useState(null);
  const [shareFavoritesOpen, setShareFavoritesOpen] = useState(false);
  const [showClearConfirm,   setShowClearConfirm]   = useState(false);
  const [editingAddr,        setEditingAddr]        = useState(null);
  const [addrDraft,          setAddrDraft]          = useState("");
  const [favorites, setFavorites] = useState(() => {
    try {
      const raw = localStorage.getItem("ewp_favorites");
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch { return new Set(); }
  });
  const [thumbsdown, setThumbsdown] = useState(() => {
    try {
      const raw = localStorage.getItem("ewp_thumbsdown");
      return raw ? new Set(JSON.parse(raw)) : new Set();
    } catch { return new Set(); }
  });

  // Advanced filters
  const [bidMin,     setBidMin]     = useState("");
  const [bidMax,     setBidMax]     = useState("");
  const [fmvMin,     setFmvMin]     = useState("");
  const [fmvMax,     setFmvMax]     = useState("");
  const [minScore,   setMinScore]   = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [fcFilter,   setFcFilter]   = useState(false);
  const [muniFilter, setMuniFilter] = useState(new Set());

  useEffect(() => {
    listDeals(0, 500)
      .then(data => setDeals(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    localStorage.setItem("ewp_favorites", JSON.stringify([...favorites]));
  }, [favorites]);

  useEffect(() => {
    localStorage.setItem("ewp_thumbsdown", JSON.stringify([...thumbsdown]));
  }, [thumbsdown]);

  const toggleThumbsUp = (saleId) => {
    if (!saleId) return;
    setFavorites(prev => {
      const next = new Set(prev);
      next.has(saleId) ? next.delete(saleId) : next.add(saleId);
      return next;
    });
    // Mutually exclusive — clear any thumbs-down on this property
    setThumbsdown(prev => { const next = new Set(prev); next.delete(saleId); return next; });
  };

  const toggleThumbsDown = (saleId) => {
    if (!saleId) return;
    setThumbsdown(prev => {
      const next = new Set(prev);
      next.has(saleId) ? next.delete(saleId) : next.add(saleId);
      return next;
    });
    // Mutually exclusive — clear any thumbs-up on this property
    setFavorites(prev => { const next = new Set(prev); next.delete(saleId); return next; });
  };

  const commitAddr = async (d) => {
    const trimmed = addrDraft.trim();
    if (!trimmed) { setEditingAddr(null); return; }
    try {
      await updateDealAddress(d.sale_id, trimmed);
      setDeals(prev => prev.map(x =>
        x.sale_id === d.sale_id ? { ...x, address: trimmed } : x
      ));
    } catch { /* non-critical */ }
    setEditingAddr(null);
  };

  const handleClear = async () => {
    await clearDeals();
    setDeals([]);
    setFavorites(new Set());
    setThumbsdown(new Set());
    setShowClearConfirm(false);
    setExpanded(null);
    clearFilters();
  };

  const clearFilters = () => {
    setFilter("ALL");
    setHideLand(false);
    setBidMin(""); setBidMax("");
    setFmvMin(""); setFmvMax("");
    setMinScore("");
    setActiveOnly(false);
    setFcFilter(false);
    setMuniFilter(new Set());
  };

  const sort = (col) => {
    if (sortCol === col) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(false); }
  };

  const isLandOnly  = (d) => d.red_flags?.some(f => f.startsWith("LAND ONLY"));
  const isPostponed = (d) => d.postponed;
  const landCount   = deals.filter(isLandOnly).length;
  const allMunis    = [...new Set(deals.map(d => d.municipality).filter(Boolean))].sort();
  const parseMoney  = (s) => { const n = parseFloat(String(s).replace(/[$,]/g, "")); return isNaN(n) ? null : n; };

  const visible = deals
    .filter(d => {
      if (filter === "FAVORITES" && !favorites.has(d.sale_id)) return false;
      if (filter !== "ALL" && filter !== "FAVORITES" && d.verdict !== filter) return false;
      if (hideLand && isLandOnly(d)) return false;
      if (activeOnly && isPostponed(d)) return false;
      if (fcFilter && d.free_and_clear === false) return false;
      const bMin = parseMoney(bidMin), bMax = parseMoney(bidMax);
      if (bMin != null && (d.min_bid ?? 0) < bMin) return false;
      if (bMax != null && (d.min_bid ?? 0) > bMax) return false;
      const fMin = parseMoney(fmvMin), fMax = parseMoney(fmvMax);
      if (fMin != null && (d.fmv ?? 0) < fMin) return false;
      if (fMax != null && (d.fmv ?? 0) > fMax) return false;
      const ms = parseMoney(minScore);
      if (ms != null && (d.score ?? 0) < ms) return false;
      if (muniFilter.size > 0 && !muniFilter.has(d.municipality)) return false;
      return true;
    })
    .sort((a, b) => {
      const av = a[sortCol] ?? 0, bv = b[sortCol] ?? 0;
      return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });

  const activeFilterCount = [
    filter !== "ALL", hideLand, activeOnly, fcFilter,
    !!bidMin, !!bidMax, !!fmvMin, !!fmvMax, !!minScore,
    muniFilter.size > 0,
  ].filter(Boolean).length;

  const VERDICTS_WITH_FAVORITES = [...VERDICTS, "FAVORITES"];

  const fmt  = (v) => v != null ? `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—";
  const fmtP = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

  // Stat counts
  const buyCount     = deals.filter(d => d.verdict === "BUY").length;
  const perfectCount = deals.filter(d => d.perfect_pass_rating === "PERFECT").length;
  const spotCount    = deals.filter(d => d.source === "spot_check").length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-charcoal">Properties</h1>
          <p className="text-sm text-gray-500 mt-1">All active deal records — sheriff sale + spot checks</p>
        </div>
        {deals.length > 0 && (
          <button
            onClick={() => setShowClearConfirm(true)}
            className="text-sm text-gray-400 hover:text-red-500 border border-brand-line hover:border-red-300 rounded-lg px-4 py-2 transition-colors"
          >
            Clear Records
          </button>
        )}
      </div>

      {/* Clear confirmation dialog */}
      {showClearConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={e => { if (e.target === e.currentTarget) setShowClearConfirm(false); }}>
          <div className="bg-white rounded-xl border border-brand-line shadow-xl w-full max-w-sm p-6 space-y-4">
            <h2 className="text-base font-bold text-brand-charcoal">Clear All Records?</h2>
            <p className="text-sm text-gray-600">
              This will permanently remove all <span className="font-semibold">{deals.length} deal records</span>.
              This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setShowClearConfirm(false)}
                className="flex-1 border border-brand-line text-gray-600 font-semibold py-2 rounded-lg hover:bg-brand-gray transition-colors text-sm">
                Cancel
              </button>
              <button onClick={handleClear}
                className="flex-1 bg-red-500 text-white font-bold py-2 rounded-lg hover:bg-red-600 transition-colors text-sm">
                Clear All
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="bg-white rounded-xl border border-brand-line p-12 text-center text-gray-400">
          Loading deals…
        </div>
      ) : deals.length === 0 ? (
        <div className="bg-white rounded-xl border border-brand-line p-12 text-center space-y-3">
          <p className="text-3xl">📋</p>
          <p className="text-brand-charcoal font-semibold">No deals yet</p>
          <p className="text-sm text-gray-500">Upload a sheriff sale PDF or run a Spot Check to get started.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary chips */}
          <div className="flex flex-wrap gap-2 items-center">
            {[
              { label: "TOTAL",   count: deals.length,  color: "bg-brand-charcoal text-white" },
              { label: "BUY",     count: buyCount,      color: "bg-verdict-buy text-white" },
              { label: "PERFECT", count: perfectCount,  color: "bg-emerald-600 text-white" },
              { label: "SPOT",    count: spotCount,     color: "bg-indigo-500 text-white" },
            ].map(({ label, count, color }) => (
              <span key={label} className={`px-3 py-1 rounded-full text-sm font-bold ${color}`}>
                {count} {label}
              </span>
            ))}
            {favorites.size > 0 && (
              <>
                <button
                  onClick={() => setFilter("FAVORITES")}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-bold border transition-colors ${filter === "FAVORITES" ? "bg-brand-charcoal border-brand-charcoal text-white" : "bg-white border-brand-charcoal text-brand-charcoal hover:bg-brand-charcoal hover:text-white"}`}
                >
                  <ThumbUp active={true} /> {favorites.size} Saved
                </button>
                <button
                  onClick={() => setShareFavoritesOpen(true)}
                  className="px-3 py-1 rounded-full text-sm font-bold border border-brand-orange text-brand-orange hover:bg-brand-orange hover:text-white transition-colors whitespace-nowrap"
                >
                  ✉ Share Saved
                </button>
              </>
            )}
          </div>

          {/* Filter bar */}
          <div className="bg-white rounded-xl border border-brand-line overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-brand-line">
              <button
                onClick={() => setShowFilters(v => !v)}
                className="flex items-center gap-2 text-sm font-semibold text-brand-charcoal hover:text-brand-orange transition-colors"
              >
                <span>{showFilters ? "▲" : "▼"}</span>
                Filters
                {activeFilterCount > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-brand-orange text-white">
                    {activeFilterCount}
                  </span>
                )}
              </button>
              <div className="flex gap-1.5 flex-wrap">
                {["ALL", ...VERDICTS_WITH_FAVORITES].map(v => (
                  <button key={v} onClick={() => setFilter(v)}
                    className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border transition-colors ${filter === v ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                    {v === "FAVORITES"
                      ? <span className="flex items-center gap-1"><ThumbUp active={favorites.size > 0} /> SAVED{favorites.size > 0 ? ` (${favorites.size})` : ""}</span>
                      : v}
                  </button>
                ))}
              </div>
              <span className="ml-auto text-xs text-gray-400">{visible.length} of {deals.length} shown</span>
              {activeFilterCount > 0 && (
                <button onClick={clearFilters} className="text-xs text-gray-400 hover:text-red-500 transition-colors">
                  Clear all
                </button>
              )}
            </div>

            {showFilters && (
              <div className="px-4 py-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">

                <div className="space-y-2">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Min Bid Range</p>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">$</span>
                      <input type="text" placeholder="Min" value={bidMin} onChange={e => setBidMin(e.target.value)}
                        className="w-full border border-brand-line rounded-lg pl-5 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-orange" />
                    </div>
                    <span className="self-center text-gray-400 text-xs">–</span>
                    <div className="relative flex-1">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">$</span>
                      <input type="text" placeholder="Max" value={bidMax} onChange={e => setBidMax(e.target.value)}
                        className="w-full border border-brand-line rounded-lg pl-5 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-orange" />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {[
                      { label: "< $10K",    min: "",      max: "10000"  },
                      { label: "$10K–$25K",  min: "10000", max: "25000"  },
                      { label: "$25K–$50K",  min: "25000", max: "50000"  },
                      { label: "$50K–$100K", min: "50000", max: "100000" },
                      { label: "> $100K",    min: "100000",max: ""       },
                    ].map(({ label, min, max }) => {
                      const active = bidMin === min && bidMax === max;
                      return (
                        <button key={label}
                          onClick={() => { setBidMin(active ? "" : min); setBidMax(active ? "" : max); }}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${active ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">FMV Range</p>
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">$</span>
                      <input type="text" placeholder="Min" value={fmvMin} onChange={e => setFmvMin(e.target.value)}
                        className="w-full border border-brand-line rounded-lg pl-5 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-orange" />
                    </div>
                    <span className="self-center text-gray-400 text-xs">–</span>
                    <div className="relative flex-1">
                      <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">$</span>
                      <input type="text" placeholder="Max" value={fmvMax} onChange={e => setFmvMax(e.target.value)}
                        className="w-full border border-brand-line rounded-lg pl-5 pr-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-orange" />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {[
                      { label: "< $50K",     min: "",       max: "50000"  },
                      { label: "$50K–$100K",  min: "50000",  max: "100000" },
                      { label: "$100K–$200K", min: "100000", max: "200000" },
                      { label: "> $200K",     min: "200000", max: ""       },
                    ].map(({ label, min, max }) => {
                      const active = fmvMin === min && fmvMax === max;
                      return (
                        <button key={label}
                          onClick={() => { setFmvMin(active ? "" : min); setFmvMax(active ? "" : max); }}
                          className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${active ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Minimum Score</p>
                    <div className="flex gap-2 items-center">
                      <input type="number" min="0" max="100" placeholder="0" value={minScore} onChange={e => setMinScore(e.target.value)}
                        className="w-20 border border-brand-line rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-orange" />
                      <div className="flex gap-1">
                        {[40, 60, 75].map(s => (
                          <button key={s} onClick={() => setMinScore(minScore === String(s) ? "" : String(s))}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${minScore === String(s) ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                            {s}+
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Property Flags</p>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={fcFilter} onChange={e => setFcFilter(e.target.checked)}
                        className="rounded border-brand-line accent-brand-orange" />
                      <span className="text-xs text-gray-700">Free &amp; Clear only</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={activeOnly} onChange={e => setActiveOnly(e.target.checked)}
                        className="rounded border-brand-line accent-brand-orange" />
                      <span className="text-xs text-gray-700">Active sales only (hide postponed)</span>
                    </label>
                    {landCount > 0 && (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={hideLand} onChange={e => setHideLand(e.target.checked)}
                          className="rounded border-brand-line accent-brand-orange" />
                        <span className="text-xs text-gray-700">Hide land-only parcels ({landCount})</span>
                      </label>
                    )}
                  </div>
                </div>

                {allMunis.length > 0 && (
                  <div className="sm:col-span-2 lg:col-span-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Municipality</p>
                      {muniFilter.size > 0 && (
                        <button onClick={() => setMuniFilter(new Set())} className="text-[11px] text-gray-400 hover:text-red-500 transition-colors">
                          Clear ({muniFilter.size} selected)
                        </button>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
                      {allMunis.map(m => {
                        const sel   = muniFilter.has(m);
                        const count = deals.filter(d => d.municipality === m).length;
                        return (
                          <button key={m}
                            onClick={() => setMuniFilter(prev => {
                              const next = new Set(prev);
                              sel ? next.delete(m) : next.add(m);
                              return next;
                            })}
                            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${sel ? "bg-brand-charcoal border-brand-charcoal text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                            {m} <span className="opacity-60">({count})</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-brand-line overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-brand-gray border-b border-brand-line">
                  <tr>
                    <Th col="score"           label="Score"      sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <th className="px-3 py-2 text-left text-xs text-gray-500 font-medium">Address</th>
                    <Th col="municipality"    label="Muni"       sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="min_bid"         label="Min Bid"    sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="max_bid_70"      label="Sweet Spot" sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="precise_mao"     label="Max Bid"    sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="fmv"             label="FMV"        sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="arv"             label="ARV"        sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="flip_net_profit" label="Flip $"     sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <Th col="cap_rate"        label="Cap%"       sortCol={sortCol} sortAsc={sortAsc} onSort={sort} />
                    <th className="px-3 py-2 text-left text-xs text-gray-500 font-medium">Verdict</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((d, i) => (
                    <>
                      <tr
                        key={d.sale_id || i}
                        className={`border-t border-brand-line hover:bg-brand-gray/50 cursor-pointer transition-opacity ${thumbsdown.has(d.sale_id) ? "opacity-40 hover:opacity-80" : ""}`}
                        onClick={() => setExpanded(expanded === i ? null : i)}
                      >
                        <td className="px-3 py-2 font-bold text-brand-orange">{d.score ?? "—"}</td>
                        <td className="px-3 py-2 text-brand-charcoal font-medium max-w-xs">
                          {editingAddr === d ? (
                            <input
                              autoFocus
                              value={addrDraft}
                              onChange={e => setAddrDraft(e.target.value)}
                              onBlur={() => commitAddr(d)}
                              onKeyDown={e => {
                                if (e.key === "Enter") commitAddr(d);
                                if (e.key === "Escape") setEditingAddr(null);
                              }}
                              onClick={e => e.stopPropagation()}
                              className="w-full text-sm font-medium border border-brand-orange rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-brand-orange"
                            />
                          ) : (
                            <div className="flex items-start gap-1 group">
                              <div className="min-w-0">
                                <p className="leading-snug">{d.address}</p>
                                {d.source === "spot_check" && (
                                  <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide bg-indigo-100 text-indigo-700 border border-indigo-200">
                                    SPOT
                                  </span>
                                )}
                                {isLandOnly(d) && (
                                  <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide bg-amber-100 text-amber-800 border border-amber-300">
                                    LAND ONLY
                                  </span>
                                )}
                              </div>
                              <button
                                onClick={e => {
                                  e.stopPropagation();
                                  setEditingAddr(d);
                                  setAddrDraft(d.address);
                                }}
                                title="Edit address"
                                className="opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 shrink-0 text-gray-400 hover:text-brand-orange text-xs leading-none"
                              >
                                ✎
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{d.municipality || "—"}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.min_bid)}</td>
                        <td className="px-3 py-2 whitespace-nowrap font-medium text-emerald-700">{fmt(d.max_bid_70)}</td>
                        <td className="px-3 py-2 whitespace-nowrap font-medium text-amber-600">{fmt(d.precise_mao)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.fmv)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.arv)}</td>
                        <td className={`px-3 py-2 whitespace-nowrap font-medium ${d.flip_net_profit > 0 ? "text-verdict-buy" : "text-verdict-nobuy"}`}>{fmt(d.flip_net_profit)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmtP(d.cap_rate)}</td>
                        <td className="px-3 py-2"><VerdictBadge verdict={d.verdict} rating={d.perfect_pass_rating} /></td>
                        <td className="px-3 py-2 text-right whitespace-nowrap">
                          {d.sale_id && (
                            <span className="inline-flex items-center gap-1 mr-1">
                              <button
                                onClick={e => { e.stopPropagation(); toggleThumbsUp(d.sale_id); }}
                                title={favorites.has(d.sale_id) ? "Remove from saved" : "Save property"}
                                className={`transition-colors ${favorites.has(d.sale_id) ? "text-brand-orange" : "text-gray-300 hover:text-brand-orange"}`}
                              >
                                <ThumbUp active={favorites.has(d.sale_id)} />
                              </button>
                              <button
                                onClick={e => { e.stopPropagation(); toggleThumbsDown(d.sale_id); }}
                                title={thumbsdown.has(d.sale_id) ? "Remove flag" : "Flag as not interested"}
                                className={`transition-colors ${thumbsdown.has(d.sale_id) ? "text-slate-500" : "text-gray-300 hover:text-slate-400"}`}
                              >
                                <ThumbDown active={thumbsdown.has(d.sale_id)} />
                              </button>
                            </span>
                          )}
                          <span className="text-gray-400">{expanded === i ? "▲" : "▼"}</span>
                        </td>
                      </tr>
                      {expanded === i && (
                        <tr key={`exp-${i}`} className="border-t border-brand-line bg-brand-gray/30">
                          <td colSpan={12} className="p-4">
                            <PropertyCard deal={d} rank={i + 1} onShare={setShareTarget} />
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {shareTarget && (
        <ShareModal deal={shareTarget} onClose={() => setShareTarget(null)} />
      )}
      {shareFavoritesOpen && (
        <ShareFavoritesModal
          deals={deals.filter(d => favorites.has(d.sale_id))}
          onClose={() => setShareFavoritesOpen(false)}
        />
      )}
    </div>
  );
}
