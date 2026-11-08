import React from 'react';
import { CARD_COLOURS } from './boardMath';

const DOT: Record<string, string> = {
  mint: 'bg-emerald-300',
  sky: 'bg-sky-300',
  amber: 'bg-amber-300',
  rose: 'bg-rose-300',
  violet: 'bg-violet-300',
};

interface Props {
  value: string | null | undefined;
  onPick: (colour: string | null) => void;
}

/** Card colour picker (token names only). Clicking the active colour clears it. */
export const ColourDots: React.FC<Props> = ({ value, onPick }) => (
  <div className="flex items-center gap-1" role="radiogroup" aria-label="Card colour">
    {Object.keys(CARD_COLOURS).map((c) => (
      <button
        key={c}
        role="radio"
        aria-checked={value === c}
        aria-label={c}
        title={c}
        onClick={() => onPick(value === c ? null : c)}
        className={`w-3 h-3 rounded-full ${DOT[c]} ${value === c ? 'ring-2 ring-ink ring-offset-1' : ''}`}
      />
    ))}
  </div>
);
