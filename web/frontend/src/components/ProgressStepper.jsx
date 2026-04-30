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

export default function ProgressStepper({ percent, message, status }) {
  const activeIdx = STEPS.findLastIndex(s => percent >= s.threshold);

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

      {/* Progress bar */}
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

      {status === "error" && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          {message}
        </div>
      )}
    </div>
  );
}
