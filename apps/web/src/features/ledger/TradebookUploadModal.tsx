import React, { useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { UploadCloud, CheckCircle2, AlertCircle, X, FileText } from 'lucide-react';
import { uploadTradebook, type ClientSummary, type UploadTradebookResponse } from '@/lib/api';
import { useEscapeKey } from '@/lib/useEscapeKey';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  clients: ClientSummary[];
  defaultClientId?: string | null;
}

export const TradebookUploadModal: React.FC<Props> = ({ isOpen, onClose, clients, defaultClientId }) => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedClientId, setSelectedClientId] = useState(defaultClientId || (clients[0]?.client_id ?? ''));
  const [broker, setBroker] = useState<'ZERODHA' | 'UPSTOX'>('ZERODHA');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadTradebookResponse | null>(null);


  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file || !selectedClientId) return;
    setUploading(true);
    setError(null);
    try {
      const res = await uploadTradebook(selectedClientId, broker, file);
      setResult(res);
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['client', selectedClientId] });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const resetAndClose = () => {
    setFile(null);
    setError(null);
    setResult(null);
    onClose();
  };
  useEscapeKey(resetAndClose, isOpen);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="w-full max-w-md bg-paper border border-hairline rounded-2xl p-6 shadow-xl relative">
        <button onClick={resetAndClose} className="absolute top-4 right-4 text-subtle hover:text-ink p-1">
          <X className="w-5 h-5" />
        </button>
        <h2 className="text-lg font-bold text-ink mb-4 flex items-center gap-2">
          <UploadCloud className="w-5 h-5 text-positive" /> Upload Broker Tradebook
        </h2>

        {result ? (
          <div className="space-y-4">
            {result.status === 'FAILED' ? (
              <div role="alert" className="flex items-center gap-2 text-negative bg-negative/10 p-3 rounded-xl text-sm font-medium">
                <X className="w-5 h-5 flex-shrink-0" /> Nothing was imported. Open the rejected rows for the reasons.
              </div>
            ) : (
              <div className="flex items-center gap-2 text-positive bg-positive/10 p-3 rounded-xl text-sm font-medium">
                <CheckCircle2 className="w-5 h-5 flex-shrink-0" /> {result.status === 'PARTIAL' ? 'Imported with some rejected rows.' : 'Import completed.'}
              </div>
            )}
            <div className="bg-canvas border border-hairline rounded-xl p-3 text-xs space-y-1 font-mono">
              <div>Total rows: {result.rows_total}</div>
              <div>Imported: {result.rows_imported}</div>
              {(result.rows_duplicate ?? 0) > 0 && <div>Already in ledger (skipped): {result.rows_duplicate}</div>}
              {result.rows_rejected > 0 && <div className="text-ember">Rejected: {result.rows_rejected}</div>}
            </div>
            <button onClick={resetAndClose} className="w-full py-2 bg-ink text-paper rounded-xl font-medium text-sm">
              Done
            </button>
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Select Client</label>
              <select
                value={selectedClientId}
                onChange={(e) => setSelectedClientId(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-hairline bg-canvas text-ink text-sm"
              >
                {clients.map((c) => (
                  <option key={c.client_id} value={c.client_id}>
                    {c.name} {c.client_code ? `(${c.client_code})` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1">Broker Format</label>
              <div className="grid grid-cols-2 gap-2">
                {(['ZERODHA', 'UPSTOX'] as const).map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => setBroker(b)}
                    className={`py-2 text-xs font-semibold rounded-xl border transition-all ${
                      broker === b ? 'border-ink bg-ink text-paper' : 'border-hairline bg-canvas text-subtle hover:text-ink'
                    }`}
                  >
                    {b}
                  </button>
                ))}
              </div>
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                isDragging ? 'border-positive bg-positive/5' : 'border-hairline hover:border-subtle bg-canvas/50'
              }`}
            >
              <input ref={fileInputRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])} />
              {file ? (
                <div className="flex items-center justify-center gap-2 text-ink font-medium">
                  <FileText className="w-5 h-5 text-positive" /> {file.name}
                </div>
              ) : (
                <div className="text-subtle text-xs space-y-1">
                  <UploadCloud className="w-6 h-6 mx-auto text-subtle/70 mb-1" />
                  <p className="font-semibold text-ink">Click to select or drag & drop a tradebook (.xlsx or .csv)</p>
                  <p>Console tradebook export format</p>
                </div>
              )}
            </div>

            {error && (
              <div className="flex items-center gap-2 text-ember text-xs bg-ember/10 p-2.5 rounded-lg">
                <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
              </div>
            )}

            <button
              onClick={handleUpload}
              disabled={!file || !selectedClientId || uploading}
              className="w-full py-2.5 bg-ink text-paper rounded-xl font-semibold text-sm disabled:opacity-40"
            >
              {uploading ? 'Ingesting & Precomputing...' : 'Ingest Tradebook'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
