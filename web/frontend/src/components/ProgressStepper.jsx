const STEPS = [
  { label: "Fetching PDF",   threshold: 5  },
  { label: "Converting",     threshold: 15 },
  { label: "Parsing",        threshold: 25 },
  { label: "Enriching",      threshold: 55 },
  { label: "Analyzing",      threshold: 60 },
  { label: "Saving",         threshold: 70 },
  { label: "Generating PDF", threshold: 80 },
  { label: "Done",           threshold: 100 },
];

// PDF generation occupies 80–99%. Break it into three phases with labels.
const PDF_PHASES = [
  { label: "Building property pages", min: 80, max: 91 },
  { label: "Rendering PDF",           min: 91, max: 96 },
  { label: "Saving PDF file",         min: 96, max: 100 },
];

function PdfSubProgress({ percent, message }) {
  // Which phase are we in?
  const phase = PDF_PHASES.findLast(p => percent >= p.min) ?? PDF_PHASES[0];
  const phaseProgress = Math.min(
    Math.round(((percent - phase.min) / (phase.max - phase.min)) * 100),
    100
  );

  // Parse "property X of N" from message if present
  const match = message?.match(/property (\d+) of (\d+)/);
  const propCurrent = match ? parseInt(match[1]) : null;
  const propTotal   = match ? parseInt(match[2]) : null;

  return (
    <div className="rounded-lg border border-brand-line bg-brand-gray p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-brand-orange animate-pulse flex-shrink-0" />
        <span className="text-xs font-semibold text-brand-charcoal">PDF Generation</span>
        <span className="ml-auto text-xs text-gray-400">{phase.label}</span>
      </div>

      {/* Phase mini-bar */}
      <div className="space-y-1">
        <div className="h-1.5 bg-brand-line rounded-full overflow-hidden">
          <div
            className="h-full bg-brand-orange rounded-full transition-all duration-500"
            style={{ width: `${phaseProgress}%` }}
          />
        </div>
      </div>

      {/* Property counter or phase message */}
      {propCurrent != null ? (
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-gray-500">
            <span>Property {propCurrent} of {propTotal}</span>
            <span>{propCurrent}/{propTotal}</span>
          </div>
          <div className="h-2 bg-brand-line rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-400 rounded-full transition-all duration-300"
              style={{ width: `${Math.round((propCurrent / propTotal) * 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-500">{message}</p>
      )}
    </div>
  );
}

export default function ProgressStepper({ percent, message, status }) {
  const activeIdx  = STEPS.findLastIndex(s => percent >= s.threshold);
  const inPdfPhase = percent >= 80 && percent < 100 && status !== "error";

  return (
    <div className="space-y-6">
      {/* Step indicators */}
      <div className="flex items-center gap-1 flex-wrap justify-center">
        {STEPS.map((step, i) => {
          const done    = i < activeIdx;
          const current = i === activeIdx;
          return (
            <div key={step.label} className="flex items-center gap-1">
              <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
                done    ? "bg-emerald-100 text-emerald-700" :
                current ? "bg-brand-orange text-white" :
                          "bg-brand-line text-gray-400"
              }`}>
                {done    && <span>✓</span>}
                {current && <span className="inline-block w-2 h-2 rounded-full bg-white animate-pulse" />}
                {step.label}
              </div>
              {i < STEPS.length - 1 && <div className="w-3 h-px bg-brand-line" />}
            </div>
          );
        })}
      </div>

      {/* Main progress bar */}
      <div className="h-3 bg-brand-line rounded-full overflow-hidden">
        <div
          className="h-full bg-brand-orange rounded-full transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-500">
        <span>{message}</span>
        <span>{percent}%</span>
      </div>

      {/* PDF sub-progress — only visible during the Generating PDF phase */}
      {inPdfPhase && <PdfSubProgress percent={percent} message={message} />}

      {status === "error" && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {message}
        </div>
      )}
    </div>
  );
}
