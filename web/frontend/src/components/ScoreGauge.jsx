export default function ScoreGauge({ score = 0, size = 120 }) {
  const pct   = Math.min(Math.max(score, 0), 100) / 100;
  const r     = 44;
  const cx    = size / 2;
  const cy    = size * 0.62;
  const circumference = Math.PI * r;

  // Arc colours: red → yellow → green
  const color =
    score >= 70 ? "#27AE60" :
    score >= 45 ? "#F5A51B" : "#E74C3C";

  // Needle angle: -180deg (0) → 0deg (100)
  const angle = -180 + pct * 180;

  return (
    <svg width={size} height={size * 0.65} viewBox={`0 0 ${size} ${size * 0.65}`}>
      {/* Background arc */}
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#E5E7EB" strokeWidth="10" strokeLinecap="round"
      />
      {/* Filled arc */}
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - pct)}
        style={{ transition: "stroke-dashoffset 0.6s ease" }}
      />
      {/* Needle */}
      <line
        x1={cx} y1={cy}
        x2={cx + Math.cos((angle * Math.PI) / 180) * (r - 8)}
        y2={cy + Math.sin((angle * Math.PI) / 180) * (r - 8)}
        stroke="#2B2B2B" strokeWidth="2.5" strokeLinecap="round"
        style={{ transition: "x2 0.6s ease, y2 0.6s ease" }}
      />
      <circle cx={cx} cy={cy} r="4" fill="#2B2B2B" />
      {/* Score label */}
      <text x={cx} y={cy - 8} textAnchor="middle" fontSize="18" fontWeight="bold" fill={color}>
        {score}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize="8" fill="#6B7280">
        / 100
      </text>
    </svg>
  );
}
