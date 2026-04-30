import ScoreGauge from "./ScoreGauge";
import VerdictBadge from "./VerdictBadge";
import MetricGrid from "./MetricGrid";
import FlipTable from "./FlipTable";
import RentalTable from "./RentalTable";
import NeighborhoodPanel from "./NeighborhoodPanel";
import RedFlagList from "./RedFlagList";

function zillowUrl(address, municipality) {
  const slug = `${address}, ${municipality}, PA`
    .replace(/[,#]/g, "")
    .trim()
    .replace(/\s+/g, "-");
  return `https://www.zillow.com/homes/${slug}_rb/`;
}

function ZillowIcon() {
  return (
    <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      <rect width="56" height="56" rx="10" fill="#006AFF"/>
      {/* House roof */}
      <polygon points="28,8 48,24 44,24 44,22 28,10 12,22 12,24 8,24" fill="white"/>
      {/* Z shape */}
      <polygon points="18,27 38,27 38,30 22,42 38,42 38,47 18,47 18,44 34,32 18,32" fill="white"/>
    </svg>
  );
}

const verdictBg = {
  BUY:      "border-verdict-buy bg-emerald-50",
  CONSIDER: "border-verdict-consider bg-amber-50",
  "NO BUY": "border-verdict-nobuy bg-red-50",
  WATCH:    "border-verdict-watch bg-orange-50",
};

export default function PropertyCard({ deal, rank }) {
  const bg = verdictBg[deal.verdict] || "border-brand-line bg-white";

  return (
    <div className={`rounded-xl border-2 ${bg} overflow-hidden`}>
      {/* Card header */}
      <div className="flex items-start justify-between px-5 py-4 bg-white border-b border-brand-line">
        <div className="flex-1 min-w-0">
          {rank != null && (
            <span className="text-xs font-bold text-brand-orange mr-2">#{rank}</span>
          )}
          <a
            href={`https://maps.google.com/?q=${encodeURIComponent(`${deal.address}, ${deal.municipality}, PA`)}`}
            target="_blank"
            rel="noreferrer"
            className="text-base font-bold text-brand-charcoal leading-snug hover:text-brand-orange underline underline-offset-2 decoration-brand-orange/50 transition-colors"
          >
            {deal.address}
          </a>
          <p className="text-xs text-gray-500 mt-0.5">
            {[deal.municipality, deal.parcel && `Parcel: ${deal.parcel}`, deal.year_built && `Built ${deal.year_built}`, deal.sqft && `${Number(deal.sqft).toLocaleString()} sqft`, deal.bedrooms && `${deal.bedrooms}BR`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="ml-4 flex-shrink-0 flex flex-col items-center gap-2">
          <a
            href={zillowUrl(deal.address, deal.municipality)}
            target="_blank"
            rel="noreferrer"
            title="View on Zillow"
            className="block w-10 h-10 rounded-lg overflow-hidden hover:opacity-80 transition-opacity shadow-sm"
          >
            <ZillowIcon />
          </a>
          <ScoreGauge score={deal.score ?? 0} size={100} />
        </div>
      </div>

      <div className="px-5 py-3 border-b border-brand-line bg-white">
        <VerdictBadge verdict={deal.verdict} rating={deal.perfect_pass_rating} />
      </div>

      {/* Metric tiles */}
      <div className="px-5 py-4 bg-white border-b border-brand-line">
        <MetricGrid deal={deal} />
      </div>

      {/* Analysis tables side-by-side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
        <div className="px-5 py-4 bg-white border-b md:border-b-0 md:border-r border-brand-line">
          <FlipTable deal={deal} />
        </div>
        <div className="px-5 py-4 bg-white border-b border-brand-line">
          <RentalTable deal={deal} />
        </div>
      </div>

      {/* Neighborhood + red flags */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
        <div className="px-5 py-4 bg-white border-b md:border-b-0 md:border-r border-brand-line">
          <NeighborhoodPanel deal={deal} />
        </div>
        <div className="px-5 py-4 bg-white border-b border-brand-line">
          <RedFlagList deal={deal} />
        </div>
      </div>

      {/* Recommendation */}
      {deal.recommendation && (
        <div className={`px-5 py-4 ${bg}`}>
          <p className="text-sm font-semibold text-brand-charcoal mb-1">Recommendation</p>
          <p className="text-sm text-gray-700">{deal.recommendation}</p>
        </div>
      )}
    </div>
  );
}
