import React from "react";

interface RiskScoreRingProps {
  score: number; // 0 to 100 or 0.0 to 1.0
  size?: number;
  strokeWidth?: number;
  className?: string;
  showLabel?: boolean;
}

export function RiskScoreRing({
  score,
  size = 80,
  strokeWidth = 6,
  className = "",
  showLabel = true,
}: RiskScoreRingProps) {
  // Normalize to 0-100
  const normalizedScore = Math.min(
    100,
    Math.max(0, Math.round(score <= 1 && score > 0 ? score * 100 : score))
  );

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (normalizedScore / 100) * circumference;

  let color = "#3E8E85"; // low risk trace-teal
  let label = "Low Risk";
  let bgGlow = "rgba(62, 142, 133, 0.15)";

  if (normalizedScore >= 70) {
    color = "#A6392E"; // signal-red
    label = "High Risk";
    bgGlow = "rgba(166, 57, 46, 0.2)";
  } else if (normalizedScore >= 40) {
    color = "#C8801F"; // signal-amber
    label = "Medium Risk";
    bgGlow = "rgba(200, 128, 31, 0.2)";
  }

  return (
    <div
      className={`relative inline-flex flex-col items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="transform -rotate-90"
      >
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#2A313C"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        {/* Value progress */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          fill="transparent"
          style={{
            filter: `drop-shadow(0 0 4px ${bgGlow})`,
            transition: "stroke-dashoffset 0.6s ease-in-out",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center select-none">
        <span className="font-mono text-lg font-bold text-white tracking-tight leading-none">
          {normalizedScore}
        </span>
        {showLabel && (
          <span
            className="text-[9px] font-medium tracking-wide uppercase mt-0.5 leading-none"
            style={{ color }}
          >
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
