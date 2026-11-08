import React, { useState } from 'react';

interface Props {
  initial: { remarks: string; risks: string };
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (patch: { remarks: string; risks: string }) => void;
}

const areaCls = 'w-full px-3 py-2 text-sm bg-canvas border border-hairline rounded-interactive text-ink focus:outline-none focus:ring-1 focus:ring-ink';

export const ThesisEditor: React.FC<Props> = ({ initial, saving, error, onCancel, onSave }) => {
  const [remarks, setRemarks] = useState(initial.remarks);
  const [risks, setRisks] = useState(initial.risks);

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ remarks, risks });
      }}
    >
      <label className="block text-[11px] font-semibold uppercase text-subtle">
        Remarks / thesis
        <textarea rows={6} className={areaCls} value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="Thesis, catalysts, things to revisit…" />
      </label>
      <label className="block text-[11px] font-semibold uppercase text-subtle">
        Risks
        <textarea rows={3} className={areaCls} value={risks} onChange={(e) => setRisks(e.target.value)} placeholder="What could go wrong…" />
      </label>
      {error && <div role="alert" className="text-xs text-negative">{error}</div>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="px-3 py-1.5 rounded-interactive bg-ink text-paper text-xs font-semibold disabled:opacity-50">
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded-interactive border border-hairline text-xs font-semibold text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
};
