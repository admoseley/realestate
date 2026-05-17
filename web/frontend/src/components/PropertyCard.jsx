import ScoreGauge from "./ScoreGauge";
import VerdictBadge from "./VerdictBadge";
import MetricGrid from "./MetricGrid";
import FlipTable from "./FlipTable";
import RentalTable from "./RentalTable";
import NeighborhoodPanel from "./NeighborhoodPanel";
import RedFlagList from "./RedFlagList";

// Street-type full words → Zillow-standard abbreviations
const STREET_ABBREVS = [
  [/\bstreet\b/gi,    'St'],
  [/\bavenue\b/gi,    'Ave'],
  [/\broad\b/gi,      'Rd'],
  [/\bdrive\b/gi,     'Dr'],
  [/\bboulevard\b/gi, 'Blvd'],
  [/\blane\b/gi,      'Ln'],
  [/\bcourt\b/gi,     'Ct'],
  [/\bplace\b/gi,     'Pl'],
  [/\bcircle\b/gi,    'Cir'],
  [/\bterrace\b/gi,   'Ter'],
  [/\bparkway\b/gi,   'Pkwy'],
  [/\bhighway\b/gi,   'Hwy'],
  [/\balley\b/gi,     'Aly'],
  [/\btrail\b/gi,     'Trl'],
];

// Regex that matches any street-type token (full word or abbreviation)
const STREET_TYPE_RE =
  /\b(street|avenue|road|drive|boulevard|lane|court|place|circle|terrace|parkway|highway|alley|trail|pike|st|ave|rd|dr|blvd|ln|ct|pl|cir|ter|pkwy|hwy|aly|trl|way)\b/gi;

function zillowUrl(address, municipality) {
  let s = address.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();

  // 1. Strip known artifacts and ward designations
  s = s.replace(/\bP\.?C\.?\b/g, '');                                    // PDF parsing artifact
  s = s.replace(/\s*[-–]\s*\d{1,2}(?:st|nd|rd|th)\b/gi, '');            // "- 19TH" ward
  s = s.replace(/\s+\d{1,2}(?:st|nd|rd|th)\s+ward\b/gi, '');            // "30TH WARD"
  s = s.replace(/\s+/g, ' ').trim();

  // 2. Pull out ZIP code if present (keep for precision)
  const zipMatch = s.match(/\b(\d{5})\b/);
  const zip = zipMatch ? zipMatch[1] : '';

  // 3. Split "street part" from embedded "city" using the last street-type
  //    token as the split point. Everything after it (before ", PA") is city.
  let streetPart = s;
  let cityPart   = municipality;

  // Find ", PA" or " PA NNNNN" suffix that marks the state
  const paIdx = s.search(/,?\s*\bPA\b\s*\d{0,5}\s*$/i);
  if (paIdx > 0) {
    const beforePA = s.slice(0, paIdx).trim();
    // Walk through all street-type matches; remember the last one
    let lastMatch = null;
    STREET_TYPE_RE.lastIndex = 0;
    let m;
    while ((m = STREET_TYPE_RE.exec(beforePA)) !== null) lastMatch = m;

    if (lastMatch) {
      const splitAt = lastMatch.index + lastMatch[0].length;
      streetPart = beforePA.slice(0, splitAt).trim();
      const remainder = beforePA.slice(splitAt).trim();
      cityPart = remainder || municipality;
    } else {
      streetPart = beforePA;
    }
  }

  // 4. Abbreviate full street-type words in the street part
  STREET_ABBREVS.forEach(([re, abbr]) => {
    streetPart = streetPart.replace(re, abbr);
  });

  // 5. Strip stray punctuation
  const clean = (t) => t.replace(/[,#&.']/g, '').replace(/\s+/g, ' ').trim();
  streetPart = clean(streetPart);
  cityPart   = clean(cityPart);

  // 6. Build slug: street · city · PA · zip (lowercase, single hyphens)
  const parts = [streetPart, cityPart, 'PA'];
  if (zip) parts.push(zip);
  const slug = parts.join(' ')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .toLowerCase();

  return `https://www.zillow.com/homes/${slug}_rb/`;
}


const verdictBg = {
  BUY:      "border-verdict-buy bg-emerald-50",
  CONSIDER: "border-verdict-consider bg-amber-50",
  "NO BUY": "border-verdict-nobuy bg-red-50",
  WATCH:    "border-verdict-watch bg-orange-50",
};

export default function PropertyCard({ deal, rank, onShare }) {
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
        <div className="ml-4 flex-shrink-0 flex items-center gap-3">
          <a
            href={zillowUrl(deal.address, deal.municipality)}
            target="_blank"
            rel="noreferrer"
            title="View on Zillow"
            className="block hover:opacity-75 transition-opacity"
          >
            <img src="/z-logo-default-visual-refresh.svg" alt="Zillow" className="w-10 h-10" />
          </a>
          {onShare && (
            <button
              onClick={() => onShare(deal)}
              title="Send to someone"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-brand-line text-gray-600 hover:border-brand-orange hover:text-brand-orange transition-colors whitespace-nowrap"
            >
              ✉ Send
            </button>
          )}
          <ScoreGauge score={deal.score ?? 0} size={100} />
        </div>
      </div>

      <div className="px-5 py-3 border-b border-brand-line bg-white">
        <VerdictBadge verdict={deal.verdict} rating={deal.perfect_pass_rating} />
      </div>

      {/* Bid Strategy */}
      <div className="px-5 py-4 bg-white border-b border-brand-line">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Bid Strategy</p>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div className="rounded-lg border border-brand-line bg-brand-gray p-3 text-center">
            <p className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Min Bid</p>
            <p className="text-lg font-bold text-brand-charcoal">
              {deal.min_bid != null ? `$${Number(deal.min_bid).toLocaleString(undefined, {maximumFractionDigits:0})}` : "—"}
            </p>
            <p className="text-[10px] text-gray-400 mt-1">Auction floor</p>
          </div>
          <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50 p-3 text-center">
            <p className="text-[10px] text-emerald-600 uppercase tracking-wide font-semibold mb-1">Sweet Spot ★</p>
            <p className="text-lg font-bold text-emerald-700">
              {deal.max_bid_70 != null ? `$${Number(deal.max_bid_70).toLocaleString(undefined, {maximumFractionDigits:0})}` : "—"}
            </p>
            <p className="text-[10px] text-emerald-600 mt-1">70% rule target</p>
          </div>
          <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-3 text-center">
            <p className="text-[10px] text-amber-600 uppercase tracking-wide font-semibold mb-1">Max Bid ⚠</p>
            <p className="text-lg font-bold text-amber-700">
              {deal.precise_mao != null ? `$${Number(deal.precise_mao).toLocaleString(undefined, {maximumFractionDigits:0})}` : "—"}
            </p>
            <p className="text-[10px] text-amber-600 mt-1">$25k profit floor</p>
          </div>
        </div>
        {deal.min_bid != null && deal.precise_mao != null && deal.max_bid_70 != null && (
          <div className="space-y-1">
            <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
              {(() => {
                const lo = deal.min_bid, hi = deal.precise_mao, sweet = deal.max_bid_70;
                const sweetPct = Math.min(100, Math.max(0, ((sweet - lo) / (hi - lo)) * 100));
                return (
                  <>
                    <div className="absolute inset-y-0 left-0 bg-emerald-400 rounded-full" style={{width: `${sweetPct}%`}} />
                    <div className="absolute inset-y-0 rounded-full bg-amber-300" style={{left:`${sweetPct}%`, right:0}} />
                  </>
                );
              })()}
            </div>
            <p className="text-[11px] text-gray-500 text-center">
              Bid between{" "}
              <span className="font-semibold text-emerald-700">${Number(deal.min_bid).toLocaleString(undefined,{maximumFractionDigits:0})}</span>
              {" "}and{" "}
              <span className="font-semibold text-emerald-700">${Number(deal.max_bid_70).toLocaleString(undefined,{maximumFractionDigits:0})}</span>
              {" "}for a strong deal — never exceed{" "}
              <span className="font-semibold text-amber-600">${Number(deal.precise_mao).toLocaleString(undefined,{maximumFractionDigits:0})}</span>.
            </p>
          </div>
        )}
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
