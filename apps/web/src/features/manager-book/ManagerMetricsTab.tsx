import React, { lazy } from 'react';
import { BookRiskTiles } from './BookRiskTiles';
import { ChartPanel } from './ChartPanel';

const BookPerformanceChart = lazy(() => import('./BookPerformanceChart'));
const ClientReturnsChart = lazy(() => import('./ClientReturnsChart'));

/** Performance tab: risk tiles, book vs market, individual client returns. */
export const ManagerMetricsTab: React.FC<{ managerId: string }> = ({ managerId }) => (
  <div className="space-y-6">
    <BookRiskTiles managerId={managerId} />
    <ChartPanel
      title="Book performance vs market"
      sub="The whole book's profit/loss against what the same money would have made in each index (index units on the book's own net invested)."
    >
      <BookPerformanceChart managerId={managerId} />
    </ChartPanel>
    <ChartPanel
      title="Individual client performance"
      sub="Each client's % return over time — normalised, since clients deploy very different capital."
    >
      <ClientReturnsChart managerId={managerId} />
    </ChartPanel>
  </div>
);
