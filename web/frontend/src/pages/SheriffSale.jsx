import { useState, useRef, useEffect } from "react";
import { sheriffSaleFromUrl, sheriffSaleUpload, pollJob, getReport, pdfUrl, debugAnalyzePdf } from "../api/client";
import ProgressStepper from "../components/ProgressStepper";
import PropertyCard from "../components/PropertyCard";
import VerdictBadge from "../components/VerdictBadge";

const DEFAULT_URL = "https://www.alleghenycounty.us/files/assets/county/v/1/government/courts/court-of-common-pleas/sheriff-office/sheriff-sale/sheriff-sale.pdf";

const VERDICTS = ["BUY", "CONSIDER", "WATCH", "NO BUY"];

export default function SheriffSale() {
  const [tab,        setTab]        = useState("upload");  // "url" | "upload"
  const [url,        setUrl]        = useState(DEFAULT_URL);
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
  const [expanded,  setExpanded]  = useState(null);
  const [hideLand,  setHideLand]  = useState(false);
  const pollRef = useRef(null);

  const startAnalysis = async () => {
    setStep("processing");
    setJob({ status: "pending", percent: 0, message: "Queued…" });
    try {
      const resp = tab === "url"
        ? await sheriffSaleFromUrl(url, enrich, fcOnly)
        : await sheriffSaleUpload(file, enrich, fcOnly);
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
        // Detect connection timeout — suggest upload instead
        if (j.message?.toLowerCase().includes("timeout") || j.message?.toLowerCase().includes("timed out")) {
          setJob(prev => ({
            ...prev,
            message: "The sheriff sale website blocked the server's download request. "
              + "Government sites often block cloud server IPs. "
              + "Please download the PDF in your browser and use the Upload File tab instead.",
          }));
        }
      }
    } catch {}
  };

  useEffect(() => () => clearInterval(pollRef.current), []);

  const reset = () => {
    clearInterval(pollRef.current);
    setStep("idle");
    setJob(null);
    setReport(null);
    setFilter("ALL");
    setExpanded(null);
    setHideLand(false);
  };

  const sort = (col) => {
    if (sortCol === col) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(false); }
  };

  const deals = report?.deals || [];
  const isLandOnly = (d) => d.red_flags?.some(f => f.startsWith("LAND ONLY"));
  const landCount  = deals.filter(isLandOnly).length;
  const visible = deals
    .filter(d => (filter === "ALL" || d.verdict === filter) && (!hideLand || !isLandOnly(d)))
    .sort((a, b) => {
      const av = a[sortCol] ?? 0, bv = b[sortCol] ?? 0;
      return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });

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
          {/* Tab toggle */}
          <div className="flex rounded-lg border border-brand-line overflow-hidden w-fit">
            {["upload", "url"].map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-5 py-2 text-sm font-medium transition-colors ${tab === t ? "bg-brand-orange text-white" : "bg-white text-gray-600 hover:bg-brand-gray"}`}>
                {t === "url" ? "PDF URL" : "Upload File"}
              </button>
            ))}
          </div>

          {tab === "upload" ? (
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
          ) : (
            <div className="space-y-3">
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-xs text-amber-800">
                <span className="text-base leading-none flex-shrink-0">⚠</span>
                <span>
                  Government and court websites often block cloud server IPs, causing download timeouts.
                  If the URL fails, switch to <strong>Upload File</strong> — download the PDF in your
                  browser first, then upload it here.
                </span>
              </div>
              <label className="block text-sm font-medium text-brand-charcoal">Sheriff Sale PDF URL</label>
              <input
                type="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                className="w-full border border-brand-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-orange"
              />
            </div>
          )}

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
            disabled={tab === "url" ? !url : !file}
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

          {/* Filter pills */}
          <div className="flex gap-2 flex-wrap items-center">
            {["ALL", ...VERDICTS].map(v => (
              <button key={v} onClick={() => setFilter(v)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${filter === v ? "bg-brand-orange border-brand-orange text-white" : "border-brand-line text-gray-600 hover:border-brand-orange"}`}>
                {v}
              </button>
            ))}
            {landCount > 0 && (
              <button
                onClick={() => setHideLand(v => !v)}
                className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors ${hideLand ? "bg-amber-500 border-amber-500 text-white" : "border-amber-300 text-amber-700 hover:border-amber-500"}`}
              >
                {hideLand ? `▲ Showing land-only (${landCount})` : `Hide Land Only (${landCount})`}
              </button>
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
