import React from 'react';

interface Props {
  title: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

export const Card: React.FC<Props> = ({ title, icon, actions, children }) => (
  <section className="bg-paper border border-hairline rounded-card p-5 shadow-sm" aria-label={title}>
    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="text-base font-semibold text-ink">{title}</h2>
      </div>
      {actions}
    </div>
    {children}
  </section>
);
