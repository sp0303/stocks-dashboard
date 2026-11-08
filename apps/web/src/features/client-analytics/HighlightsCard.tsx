import React from 'react';
import { Sparkles } from 'lucide-react';
import type { Highlight } from '@/lib/apiAnalytics';
import { Card } from './Card';
import { highlightText } from './highlightText';

export const HighlightsCard: React.FC<{ items: Highlight[] }> = ({ items }) => (
  <Card title="Holding highlights" icon={<Sparkles className="w-5 h-5 text-subtle" aria-hidden />}>
    {items.length === 0 ? (
      <p className="text-xs text-subtle">No holdings or closed trades yet.</p>
    ) : (
      <ul className="space-y-1.5 text-sm">
        {items.map((h) => {
          const { label, text } = highlightText(h);
          return (
            <li key={h.kind} className="text-ink">
              <b>{label}:</b> <span className={h.value != null && h.value < 0 ? 'text-negative' : ''}>{text}</span>
            </li>
          );
        })}
      </ul>
    )}
  </Card>
);
