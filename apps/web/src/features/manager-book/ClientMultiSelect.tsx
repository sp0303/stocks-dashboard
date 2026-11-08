import React from 'react';

interface Props {
  clients: { client_id: string; name: string }[];
  selected: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
}

/** Chip-style multi-select; nothing selected means "all clients". */
export const ClientMultiSelect: React.FC<Props> = ({ clients, selected, onChange }) => {
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };
  const chip = (on: boolean) =>
    `px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
      on ? 'bg-ink text-paper border-ink' : 'bg-paper text-ink border-hairline hover:bg-canvas'
    }`;
  return (
    <div role="group" aria-label="Clients to include" className="flex flex-wrap gap-1.5">
      <button type="button" aria-pressed={selected.size === 0} className={chip(selected.size === 0)} onClick={() => onChange(new Set())}>
        All clients
      </button>
      {clients.map((c) => (
        <button key={c.client_id} type="button" aria-pressed={selected.has(c.client_id)} className={chip(selected.has(c.client_id))} onClick={() => toggle(c.client_id)}>
          {c.name}
        </button>
      ))}
    </div>
  );
};
