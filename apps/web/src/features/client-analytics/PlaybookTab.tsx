import React, { useState } from 'react';
import { BookOpen, Download } from 'lucide-react';
import { exportPlaybookCsv, type Pool } from '@/lib/apiAnalytics';
import { AnalyticsGate } from './AnalyticsGate';
import { Card } from './Card';
import { PlaybookTable } from './PlaybookTable';
import { Segmented } from './Segmented';
import { downloadBlob } from './downloadBlob';
import { POOLS } from './pools';
import { usePlaybook } from './useAnalytics';

const PlaybookTab: React.FC<{ clientId: string }> = ({ clientId }) => {
  const [pool, setPool] = useState<Pool>('delivery');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const q = usePlaybook(clientId, pool);
  const rows = q.data?.data ?? [];

  const onExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      downloadBlob(await exportPlaybookCsv(clientId), `playbook_${clientId}_${new Date().toISOString().slice(0, 10)}.csv`);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="Trade pool" value={pool} options={POOLS} onChange={setPool} />
      <button
        type="button"
        onClick={onExport}
        disabled={exporting}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-interactive border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas disabled:opacity-50"
      >
        <Download className="w-3.5 h-3.5 text-subtle" aria-hidden /> {exporting ? 'Exporting…' : 'Export CSV'}
      </button>
    </div>
  );
  return (
    <Card title="Playbook (round trips by stock)" icon={<BookOpen className="w-5 h-5 text-subtle" aria-hidden />} actions={actions}>
      {exportError && <p role="alert" className="mb-3 text-xs text-negative">{exportError}</p>}
      <AnalyticsGate isLoading={q.isLoading} error={q.error} onRetry={() => q.refetch()} empty={rows.length === 0} emptyTitle={`No closed ${pool} trades`}>
        <PlaybookTable rows={rows} />
      </AnalyticsGate>
    </Card>
  );
};

export default PlaybookTab;
