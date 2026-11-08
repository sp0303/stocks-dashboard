import React from 'react';

interface Option {
  id: string;
  name: string;
}

interface Props {
  label: string;
  options: Option[];
  /** null = all selected (the default, as in v1). */
  selected: Set<string> | null;
  onChange: (next: Set<string> | null) => void;
}

/** Toggle chips; "All" resets to null so newly added clients/lists are included automatically. */
export const BoardFilters: React.FC<Props> = ({ label, options, selected, onChange }) => {
  if (options.length === 0) return null;
  const isOn = (id: string) => selected === null || selected.has(id);
  const toggle = (id: string) => {
    const next = new Set(selected ?? options.map((o) => o.id));
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next.size === options.length ? null : next);
  };
  const chip = 'px-2.5 py-1 rounded-full border text-[11px] transition-colors';
  return (
    <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label={label}>
      <span className="text-[11px] font-semibold text-subtle uppercase tracking-wider mr-1">{label}</span>
      <button
        onClick={() => onChange(null)}
        aria-pressed={selected === null}
        className={`${chip} ${selected === null ? 'bg-ink text-paper border-ink' : 'border-hairline text-subtle'}`}
      >
        All
      </button>
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => toggle(o.id)}
          aria-pressed={isOn(o.id)}
          className={`${chip} ${isOn(o.id) ? 'bg-canvas text-ink border-subtle/40' : 'border-hairline text-subtle/60 line-through'}`}
        >
          {o.name}
        </button>
      ))}
    </div>
  );
};
