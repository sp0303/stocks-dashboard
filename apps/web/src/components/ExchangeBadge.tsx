import React from 'react';

/** Symbol with a separate small exchange badge (R6: a holding is keyed by symbol AND exchange).
 *  The sr-only separator keeps copied / screen-read text as "CARTRADE · NSE", never "CARTRADENSE". */
export const SymbolWithExchange: React.FC<{ symbol: string; exchange?: string | null; className?: string }> = ({
  symbol,
  exchange,
  className = '',
}) => (
  <span className={`inline-flex items-center gap-1.5 ${className}`}>
    <span>{symbol}</span>
    {exchange && (
      <>
        <span className="sr-only"> · </span>
        <span
          className="inline-block text-[10px] leading-none font-semibold tracking-wide px-1.5 py-1 rounded-md bg-canvas text-subtle border border-hairline"
          title={`Listed on ${exchange}`}
        >
          {exchange}
        </span>
      </>
    )}
  </span>
);
