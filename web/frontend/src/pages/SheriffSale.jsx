import { useState, useRef, useEffect } from "react";
import { sheriffSaleUpload, pollJob, getReport, pdfUrl, debugAnalyzePdf } from "../api/client";
import ProgressStepper from "../components/ProgressStepper";
import PropertyCard from "../components/PropertyCard";
import VerdictBadge from "../components/VerdictBadge";

const VERDICTS = ["BUY", "CONSIDER", "WATCH", "NO BUY"];

export default function SheriffSale() {
  const [file,       setFile]       = useState(null);
  const [enrich,     setEnrich]     = useState(true);
  const [fcOnly,     setFcOnly]     = useState(true);
  const [debugging,  setDebugging]  = useState(false);
  const [step,    setStep]    = useState("idle"); // idle | processing | results
  const [job,     setJob]     = useState(null);
  const [report,  setReport]  = useState(null);
  const [filter,  setFilter]  = useState("ALL");
  const [sortCol, setSortCol] = useState("score");
  const [sortAsc, setSortAsc] = useState(false);
  const [expanded,    setExpanded]    = useState(null);
  const [hideLand,    setHideLand]    = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  // Advanced filters
  const [bidMin,      setBidMin]      = useState("");
  const [bidMax,      setBidMax]      = useState("");
  const [fmvMin,      setFmvMin]      = useState("");
  const [fmvMax,      setFmvMax]      = useState("");
  const [minScore,    setMinScore]    = useState("");
  const [activeOnly,  setActiveOnly]  = useState(false);
  const [muniFilter,  setMuniFilter]  = useState(new Set());
  const pollRef = useRef(null);

  const startAnalysis = async () => {
    setStep("processing");
    setJob({ status: "pending", percent: 0, message: "Queued…" });
    try {
      const resp = await sheriffSaleUpload(file, enrich, fcOnly);
      pollRef.current = setInterval(() => tick(resp.job_id), 2000);
    } catch (e) {
      setJob({ status: "error", percent: 0, message: e.response?.data?.detail || "Failed to start job" });
    }
  };

  const tick = async (jobId) => {
    try {
      const j = await pollJob(jobId);
      setJob(j);
      if (j.status === "done") {
        clearInterval(pollRef.current);
        const r = await getReport(j.report_id);
        setReport(r);
        setStep("results");
      } else if (j.status === "error") {
        clearInterval(pollRef.current);
      }
    } catch {}
  };

  useEffect(() => () => clearInterval(pollRef.current), []);

  const clearFilters = () => {
    setFilter("ALL");
    setHideLand(false);
    setBidMin(""); setBidMax("");
    setFmvMin(""); setFmvMax("");
    setMinScore("");
    setActiveOnly(false);
    setMuniFilter(new Set());
  };

  const reset = () => {
    clearInterval(pollRef.current);
    setStep("idle");
    setJob(null);
    setReport(null);
    setExpanded(null);
    setShowFilters(false);
    clearFilters();
  };

  const sort = (col) => {
    if (sortCol === col) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(false); }
  };

  const deals = report?.deals || [];
  const isLandOnly  = (d) => d.red_flags?.some(f => f.startsWith("LAND ONLY"));
  const isPostponed = (d) => d.postponed;
  const landCount   = deals.filter(isLandOnly).length;

  // Sorted muni list derived from loaded deals
  const allMunis = [...new Set(deals.map(d => d.municipality).filter(Boolean))].sort();

  const parseMoney = (s) => { const n = parseFloat(String(s).replace(/[$,]/g, "")); return isNaN(n) ? null : n; };

  const visible = deals
    .filter(d => {
      if (filter !== "ALL" && d.verdict !== filter) return false;
      if (hideLand && isLandOnly(d)) return false;
      if (activeOnly && isPostponed(d)) return false;
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

  // Count active non-default filters for badge
  const activeFilterCount = [
    filter !== "ALL",
    hideLand,
    activeOnly,
    !!bidMin, !!bidMax,
    !!fmvMin, !!fmvMax,
    !!minScore,
    muniFilter.size > 0,
  ].filter(Boolean).length;

  const Th = ({ col, label }) => (
    <th
      className="px-3 py-2 text-left text-xs text-gray-500 font-medium cursor-pointer hover:text-brand-charcoal whitespace-nowrap"
      onClick={() => sort(col)}
    >
      {label} {sortCol === col ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );

  const fmt  = (v) => v != null ? `$${Number(v).toLocaleString(undefined,{maximumFractionDigits:0})}` : "—";
  const fmtP = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

  const DebugButton = () => (
    <label className={`inline-flex items-center gap-2 text-xs font-semibold cursor-pointer px-3 py-2 rounded-lg border transition-colors ${
      debugging ? "border-gray-300 text-gray-400 cursor-default" : "border-brand-line text-gray-500 hover:border-brand-orange hover:text-brand-orange"
    }`}>
      {debugging ? "⏳ Generating debug report…" : "⬇ Download Debug Report"}
      <input
        type="file" accept=".pdf" className="hidden"
        disabled={debugging}
        onChange={async (e) => {
          const f = e.target.files[0];
          if (!f) return;
          setDebugging(true);
          try { await debugAnalyzePdf(f); }
          catch (err) { alert("Debug failed: " + (err.message || "Unknown error")); }
          finally { setDebugging(false); e.target.value = ""; }
        }}
      />
    </label>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-charcoal">Sheriff Sale Analysis</h1>
          <p className="text-sm text-gray-500 mt-1">Batch-analyze the Allegheny County sheriff sale PDF</p>
        </div>
        {step !== "idle" && (
          <button onClick={reset} className="text-sm text-gray-500 hover:text-brand-charcoal border border-brand-line rounded-lg px-4 py-2">
            ← New Analysis
          </button>
        )}
      </div>

      {/* ── Step 1: Input ── */}
      {step === "idle" && (
        <div className="bg-white rounded-xl border border-brand-line p-6 space-y-5">
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              Download the sheriff sale PDF from{" "}
              <a href="https://sheriffalleghenycounty.com" target="_blank" rel="noreferrer"
                className="text-brand-orange hover:underline font-medium">
                sheriffalleghenycounty.com
              </a>{" "}
              or the Allegheny County website, then upload it here.
            </p>
            <div
              className="border-2 border-dashed border-brand-orange rounded-xl p-10 text-center cursor-pointer hover:bg-brand-tint transition-colors"
              onClick={() => document.getElementById("pdf-input").click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); setFile(e.dataTransfer.files[0]); }}
            >
              <input id="pdf-input" type="file" accept=".pdf" className="hidden" onChange={e => setFile(e.target.files[0])} />
              {file ? (
                <div className="space-y-1">
                  <p className="text-brand-orange text-2xl">✓</p>
                  <p className="text-brand-charcoal font-semibold">{file.name}</p>
                  <p className="text-xs text-gray-400">{(file.size / 1024 / 1024).toFixed(1)} MB · click to change</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-3xl">📄</p>
                  <p className="text-gray-500 text-sm">Drag & drop the sheriff sale PDF here</p>
                  <p className="text-brand-orange font-semibold text-sm">or click to browse</p>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <div
                onClick={() => setFcOnly(v => !v)}
                className={`w-10 h-6 rounded-full transition-colors ${fcOnly ? "bg-brand-orange" : "bg-brand-line"} relative flex-shrink-0`}
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${fcOnly ? "left-5" : "left-1"}`} />
              </div>
              <div>
                <span className="text-sm text-gray-700 font-medium">Free &amp; Clear properties only</span>
                <p className="text-xs text-gray-400 mt-0.5">
                  {fcOnly
                    ? "Only analyzing F&C properties — best investment candidates with no lender debt."
                    : "Analyzing all properties — includes regular foreclosures (lender owed money)."}
                </p>
              </div>
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <div
                onClick={() => setEnrich(e => !e)}
                className={`w-10 h-6 rounded-full transition-colors ${enrich ? "bg-brand-orange" : "bg-brand-line"} relative flex-shrink-0`}
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${enrich ? "left-5" : "left-1"}`} />
              </div>
              <div>
                <span className="text-sm text-gray-700 font-medium">Auto-enrich property data</span>
                <p className="text-xs text-gray-400 mt-0.5">Looks up FMV, sqft, year built from WPRDC. Slower but more accurate.</p>
              </div>
            </label>
          </div>

          <button
            onClick={startAnalysis}
            disabled={!file}
            className="bg-brand-orange text-white font-bold px-8 py-3 rounded-xl disabled:opacity-40 hover:bg-brand-dark transition-colors"
          >
            Start Analysis
          </button>
        </div>
      )}

      {/* ── Step 2: Processing ── */}
      {step === "processing" && job && (
        <div className="bg-white rounded-xl border border-brand-line p-8 space-y-6">
          <h2 className="text-lg font-semibold text-brand-charcoal">Analyzing sheriff sale…</h2>
          <ProgressStepper percent={job.percent} message={job.message} status={job.status} />
          {job.status === "error" && (
            <div className="pt-2 border-t border-brand-line flex items-center gap-3">
              <span className="text-xs text-gray-500">Upload the same PDF to get a detailed diagnostic:</span>
              <DebugButton />
            </div>
          )}
        </div>
      )}

      {/* ── Step 3: Results ── */}
      {step === "results" && report && (
        <div className="space-y-5">
          {/* Summary chips */}
          <div className="flex flex-wrap gap-2 items-center">
            {[
              { label: "BUY",      count: report.buy_count,      color: "bg-verdict-buy text-white" },
              { label: "CONSIDER", count: report.consider_count, color: "bg-verdict-consider text-white" },
              { label: "WATCH",    count: report.watch_count,    color: "bg-verdict-watch text-white" },
              { label: "NO BUY",   count: report.no_buy_count,   color: "bg-verdict-nobuy text-white" },
              { label: "PERFECT",  count: report.perfect_count,  color: "bg-emerald-600 text-white" },
            ].map(({ label, count, color }) => (
              <span key={label} className={`px-3 py-1 rounded-full text-sm font-bold ${color}`}>
                {count} {label}
              </span>
            ))}
            <div className="ml-auto flex items-center gap-3">
              <DebugButton />
              <a href={pdfUrl(report.id)} target="_blank" rel="noreferrer"
                className="bg-brand-charcoal text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-black transition-colors">
                ↓ Download PDF
              </a>
            </div>
          </div>

          {/* Filter bar */}
          <div className="bg-white rounded-xl border border-brand-line overflow-hidden">
            {/* Header row */}
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
              {/* Verdict pills always visible */}
              <div className="flex gap-1.5 flex-wrap">
                {["ALL", ...VERDICTS].map(v => (
                  <button key={v} onClick={() => setFilter(v)}
                    className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border transition-colors ${filter === v ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                    {v}
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

            {/* Expanded filter panel */}
            {showFilters && (
              <div className="px-4 py-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">

                {/* Min Bid range */}
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
                  {/* Preset buttons */}
                  <div className="flex flex-wrap gap-1">
                    {[
                      { label: "< $10K",        min: "",      max: "10000"  },
                      { label: "$10K–$25K",      min: "10000", max: "25000"  },
                      { label: "$25K–$50K",      min: "25000", max: "50000"  },
                      { label: "$50K–$100K",     min: "50000", max: "100000" },
                      { label: "> $100K",        min: "100000",max: ""       },
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

                {/* FMV range */}
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
                      { label: "< $50K",        min: "",       max: "50000"  },
                      { label: "$50K–$100K",     min: "50000",  max: "100000" },
                      { label: "$100K–$200K",    min: "100000", max: "200000" },
                      { label: "> $200K",        min: "200000", max: ""       },
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

                {/* Score + toggles */}
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

                {/* Municipality multi-select */}
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
                        const sel = muniFilter.has(m);
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
                    <Th col="score"          label="Score" />
                    <th className="px-3 py-2 text-left text-xs text-gray-500 font-medium">Address</th>
                    <Th col="municipality"   label="Muni" />
                    <Th col="min_bid"        label="Min Bid" />
                    <Th col="fmv"            label="FMV" />
                    <Th col="arv"            label="ARV" />
                    <Th col="flip_net_profit" label="Flip $" />
                    <Th col="cap_rate"       label="Cap%" />
                    <th className="px-3 py-2 text-left text-xs text-gray-500 font-medium">Verdict</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((d, i) => (
                    <>
                      <tr
                        key={d.sale_id || i}
                        className="border-t border-brand-line hover:bg-brand-gray/50 cursor-pointer"
                        onClick={() => setExpanded(expanded === i ? null : i)}
                      >
                        <td className="px-3 py-2 font-bold text-brand-orange">{d.score ?? "—"}</td>
                        <td className="px-3 py-2 text-brand-charcoal font-medium max-w-xs">
                          <p className="leading-snug">{d.address}</p>
                          {isLandOnly(d) && (
                            <span className="inline-block mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide bg-amber-100 text-amber-800 border border-amber-300">
                              LAND ONLY
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{d.municipality || "—"}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.min_bid)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.fmv)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmt(d.arv)}</td>
                        <td className={`px-3 py-2 whitespace-nowrap font-medium ${d.flip_net_profit > 0 ? "text-verdict-buy" : "text-verdict-nobuy"}`}>{fmt(d.flip_net_profit)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{fmtP(d.cap_rate)}</td>
                        <td className="px-3 py-2"><VerdictBadge verdict={d.verdict} rating={d.perfect_pass_rating} /></td>
                        <td className="px-3 py-2 text-gray-400">{expanded === i ? "▲" : "▼"}</td>
                      </tr>
                      {expanded === i && (
                        <tr key={`exp-${i}`} className="border-t border-brand-line bg-brand-gray/30">
                          <td colSpan={10} className="p-4">
                            <PropertyCard deal={d} rank={i + 1} />
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
    </div>
  );
}
