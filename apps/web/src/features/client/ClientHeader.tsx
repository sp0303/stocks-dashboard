import React, { useState } from 'react';
import { ArrowLeft, Download } from 'lucide-react';
import { exportTradebookCsv, type ClientSummary } from '@/lib/api';

interface Props {
  clientId: string;
  overview: ClientSummary;
  onBack: () => void;
}

export const ClientHeader: React.FC<Props> = ({ clientId, overview, onBack }) => {
  const [downloading, setDownloading] = useState(false);

  // R14: authenticated fetch + blob, never a bare link.
  const handleDownloadCsv = async () => {
    setDownloading(true);
    try {
      const blob = await exportTradebookCsv(clientId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tradebook_${clientId}_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Failed to export CSV', e);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <button onClick={onBack} className="flex items-center gap-2 text-xs font-semibold text-subtle hover:text-ink transition-colors mb-2">
          <ArrowLeft className="w-4 h-4" aria-hidden /> Back to Manager Book
        </button>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-ink">{overview.name}</h1>
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-canvas text-subtle border border-hairline">
            {overview.broker || 'Direct'} {overview.client_code ? `· ${overview.client_code}` : ''}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={handleDownloadCsv}
          disabled={downloading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-hairline bg-paper text-xs font-semibold text-ink hover:bg-canvas transition-colors disabled:opacity-50"
          title="Download lossless audit-ready tradebook (Rule R14)"
        >
          <Download className="w-3.5 h-3.5 text-subtle" aria-hidden />
          {downloading ? 'Downloading...' : 'Export Tradebook (R14)'}
        </button>
        {overview.as_of && (
          <span className="text-xs text-subtle hidden sm:inline">
            As of <strong className="text-ink">{overview.as_of}</strong>
          </span>
        )}
      </div>
    </div>
  );
};
