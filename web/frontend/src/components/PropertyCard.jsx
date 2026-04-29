import ScoreGauge from "./ScoreGauge";
import VerdictBadge from "./VerdictBadge";
import MetricGrid from "./MetricGrid";
import FlipTable from "./FlipTable";
import RentalTable from "./RentalTable";
import NeighborhoodPanel from "./NeighborhoodPanel";
import RedFlagList from "./RedFlagList";

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
          <p className="text-base font-bold text-brand-charcoal leading-snug">{deal.address}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {[deal.municipality, deal.parcel && `Parcel: ${deal.parcel}`, deal.year_built && `Built ${deal.year_built}`, deal.sqft && `${Number(deal.sqft).toLocaleString()} sqft`, deal.bedrooms && `${deal.bedrooms}BR`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="ml-4 flex-shrink-0 text-center">
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
