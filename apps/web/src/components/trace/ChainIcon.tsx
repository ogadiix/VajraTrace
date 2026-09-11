import React from "react";

interface ChainIconProps {
  chain: string;
  className?: string;
}

export function ChainIcon({ chain, className = "w-4 h-4" }: ChainIconProps) {
  const normalized = chain.toUpperCase();

  if (normalized === "ETH" || normalized === "ETHEREUM") {
    return (
      <svg
        viewBox="0 0 32 32"
        fill="currentColor"
        className={className}
        aria-label="Ethereum"
      >
        <path
          fill="currentColor"
          d="M16 2.5L7 17.5L16 22L25 17.5L16 2.5ZM16 23.5L7 19L16 29.5L25 19L16 23.5Z"
        />
      </svg>
    );
  }

  if (normalized === "BTC" || normalized === "BITCOIN") {
    return (
      <svg
        viewBox="0 0 32 32"
        fill="currentColor"
        className={className}
        aria-label="Bitcoin"
      >
        <path
          fill="currentColor"
          d="M19.5 13.5C20.3 12.8 20.8 11.7 20.5 10.3C20.1 8.6 18.6 7.5 16.5 7.5H11V24.5H17.2C19.6 24.5 21.4 23.1 21.7 21C22 19.1 21 17.5 19.5 16.8V16.7C20.4 16 21 14.9 20.8 13.7C20.6 12.8 20.1 12 19.5 11.5V13.5ZM14.5 10.8H16.2C17.3 10.8 18 11.3 18 12.3C18 13.3 17.3 13.8 16.2 13.8H14.5V10.8ZM16.8 21.2H14.5V17.2H16.8C18 17.2 18.8 17.8 18.8 19.2C18.8 20.6 18 21.2 16.8 21.2Z"
        />
      </svg>
    );
  }

  if (normalized === "TRON" || normalized === "TRX") {
    return (
      <svg
        viewBox="0 0 32 32"
        fill="currentColor"
        className={className}
        aria-label="TRON"
      >
        <path
          fill="currentColor"
          d="M4 6L28 10L19 28L4 6ZM7.5 8.5L18 24.2L24.8 11.2L7.5 8.5Z"
        />
      </svg>
    );
  }

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v12M6 12h12" />
    </svg>
  );
}
