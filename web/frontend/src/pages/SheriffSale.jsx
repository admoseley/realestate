import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { sheriffSaleUpload, pollJob, getReport, pdfUrl, debugAnalyzePdf } from "../api/client";
import ProgressStepper from "../components/ProgressStepper";

const DebugButton = ({ debugging, setDebugging }) => (
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

export default function SheriffSale() {
  const navigate = useNavigate();
  const [file,      setFile]      = useState(null);
  const [enrich,    setEnrich]    = useState(true);
  const [debugging, setDebugging] = useState(false);
  const [step,   setStep]   = useState("idle"); // idle | processing | results
  const [job,    setJob]    = useState(null);
  const [report, setReport] = useState(null);
  const pollRef = useRef(null);

  const startAnalysis = async () => {
    setStep("processing");
    setJob({ status: "pending", percent: 0, message: "Queued…" });
    try {
      const resp = await sheriffSaleUpload(file, enrich);
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
    } catch { /* poll error — transient, ignore */ }
  };

  useEffect(() => () => clearInterval(pollRef.current), []);

  const reset = () => {
    clearInterval(pollRef.current);
    setStep("idle");
    setJob(null);
    setReport(null);
    setFile(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-charcoal">Sheriff Sale Upload</h1>
          <p className="text-sm text-gray-500 mt-1">Upload the Allegheny County sheriff sale PDF to ingest or update deals</p>
        </div>
        {step !== "idle" && (
          <button onClick={reset} className="text-sm text-gray-500 hover:text-brand-charcoal border border-brand-line rounded-lg px-4 py-2">
            ← Upload Another
          </button>
        )}
      </div>

      {/* Step 1: Upload */}
      {step === "idle" && (
        <div className="bg-white rounded-xl border border-brand-line p-6 space-y-5">
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              Download the sheriff sale PDF from{" "}
              <a href="https://sheriffalleghenycounty.com" target="_blank" rel="noreferrer"
                className="text-brand-orange hover:underline font-medium">
                sheriffalleghenycounty.com
              </a>{" "}
              then upload it here. New entries are added to your deal list; existing records are updated only if the listing changed.
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

      {/* Step 2: Processing */}
      {step === "processing" && job && (
        <div className="bg-white rounded-xl border border-brand-line p-8 space-y-6">
          <h2 className="text-lg font-semibold text-brand-charcoal">Analyzing sheriff sale…</h2>
          <ProgressStepper percent={job.percent} message={job.message} status={job.status} />
          {job.status === "error" && (
            <div className="pt-2 border-t border-brand-line flex items-center gap-3">
              <span className="text-xs text-gray-500">Upload the same PDF to get a detailed diagnostic:</span>
              <DebugButton debugging={debugging} setDebugging={setDebugging} />
            </div>
          )}
        </div>
      )}

      {/* Step 3: Completion summary */}
      {step === "results" && report && (
        <div className="bg-white rounded-xl border border-brand-line p-8 space-y-5 text-center">
          <p className="text-4xl">✓</p>
          <h2 className="text-xl font-bold text-brand-charcoal">Analysis Complete</h2>
          <p className="text-gray-500 text-sm">{job?.message}</p>
          <div className="flex flex-wrap gap-2 justify-center">
            {[
              { label: "BUY",     count: report.buy_count,      color: "bg-verdict-buy" },
              { label: "CONSIDER",count: report.consider_count, color: "bg-verdict-consider" },
              { label: "WATCH",   count: report.watch_count,    color: "bg-verdict-watch" },
              { label: "NO BUY",  count: report.no_buy_count,   color: "bg-verdict-nobuy" },
              { label: "PERFECT", count: report.perfect_count,  color: "bg-emerald-600" },
            ].map(({ label, count, color }) => (
              <span key={label} className={`px-3 py-1 rounded-full text-sm font-bold text-white ${color}`}>
                {count} {label}
              </span>
            ))}
          </div>
          <div className="flex gap-3 justify-center pt-2">
            <a href={pdfUrl(report.id)} target="_blank" rel="noreferrer"
              className="bg-brand-charcoal text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-black transition-colors">
              ↓ Download PDF
            </a>
            <button
              onClick={() => navigate("/")}
              className="bg-brand-orange text-white font-bold px-6 py-2 rounded-xl hover:bg-brand-dark transition-colors"
            >
              View on Dashboard →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
