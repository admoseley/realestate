const VERDICT_COLORS = {
  BUY:      "bg-verdict-buy text-white",
  CONSIDER: "bg-verdict-consider text-white",
  "NO BUY": "bg-verdict-nobuy text-white",
  WATCH:    "bg-verdict-watch text-white",
};

const RATING_COLORS = {
  PERFECT:  "bg-emerald-100 text-emerald-800 border border-emerald-300",
  PASS:     "bg-blue-100 text-blue-800 border border-blue-300",
  MARGINAL: "bg-yellow-100 text-yellow-800 border border-yellow-300",
  AVOID:    "bg-red-100 text-red-800 border border-red-300",
  WATCH:    "bg-orange-100 text-orange-800 border border-orange-300",
};

export default function VerdictBadge({ verdict, rating }) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {verdict && (
        <span className={`px-3 py-1 rounded-full text-sm font-bold ${VERDICT_COLORS[verdict] || "bg-gray-400 text-white"}`}>
          {verdict}
        </span>
      )}
      {rating && (
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${RATING_COLORS[rating] || "bg-gray-100 text-gray-700"}`}>
          {rating}
        </span>
      )}
    </div>
  );
}
