import React, { Suspense } from 'react';
import { LoadingBlock } from '@/components/QueryStates';

interface Props {
  title: string;
  sub: string;
  children: React.ReactNode;
}

/** Card wrapper with a Suspense boundary for a lazily loaded chart. */
export const ChartPanel: React.FC<Props> = ({ title, sub, children }) => (
  <section className="bg-paper border border-hairline rounded-card p-5 shadow-sm">
    <h2 className="text-base font-semibold text-ink">{title}</h2>
    <p className="text-xs text-subtle mb-3">{sub}</p>
    <Suspense fallback={<LoadingBlock rows={4} label={`Loading ${title}`} />}>{children}</Suspense>
  </section>
);
