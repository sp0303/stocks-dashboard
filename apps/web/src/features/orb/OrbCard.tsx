import React from 'react';

interface Props {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}

export const OrbCard: React.FC<Props> = ({ title, aside, children }) => (
  <section className="bg-paper border border-hairline rounded-card p-5 space-y-3" aria-label={title}>
    <header className="flex items-center justify-between gap-3 flex-wrap">
      <h2 className="text-sm font-bold text-ink uppercase tracking-wide">{title}</h2>
      {aside && <div className="text-xs text-subtle">{aside}</div>}
    </header>
    {children}
  </section>
);
