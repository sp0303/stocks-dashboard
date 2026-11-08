interface Props<T extends string> {
  label: string;
  value: T;
  options: { key: T; label: string; title?: string }[];
  onChange: (v: T) => void;
}

/** Small segmented control (radio group semantics, keyboard reachable). */
export function Segmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex items-center gap-1 p-1 rounded-interactive border border-hairline bg-canvas">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          title={o.title}
          onClick={() => onChange(o.key)}
          className={`px-3 py-1 rounded-interactive text-xs font-semibold transition-colors ${
            value === o.key ? 'bg-ink text-paper' : 'text-subtle hover:text-ink'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
