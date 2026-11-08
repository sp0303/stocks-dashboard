import React, { useState } from 'react';
import { apiChangePassword } from '@/lib/api';

export const MIN_PASSWORD_LEN = 8; // matches ChangePasswordRequest on the API

const inputCls = 'w-full mt-1 px-3 py-2 rounded-interactive border border-hairline bg-paper text-ink text-sm focus:outline-none focus:ring-2 focus:ring-accent/30';

export function validatePasswordChange(current: string, next: string, confirm: string): string | null {
  if (!current) return 'Enter your current password.';
  if (next.length < MIN_PASSWORD_LEN) return `New password must be at least ${MIN_PASSWORD_LEN} characters.`;
  if (next === current) return 'New password must differ from the current one.';
  if (next !== confirm) return 'New passwords do not match.';
  return null;
}

const Field: React.FC<{ label: string; auto: string; value: string; onChange: (v: string) => void }> = ({ label, auto, value, onChange }) => (
  <label className="block text-xs font-semibold text-subtle">
    {label}
    <input type="password" autoComplete={auto} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)} />
  </label>
);

/** Current + new + confirm, validated client-side, then POST /auth/change-password. */
export const ChangePasswordForm: React.FC<{ onDone: () => void }> = ({ onDone }) => {
  const [f, setF] = useState({ current: '', next: '', confirm: '' });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = validatePasswordChange(f.current, f.next, f.confirm);
    if (v) return setError(v);
    setBusy(true);
    setError(null);
    try {
      await apiChangePassword(f.current, f.next);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not change password');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <Field label="Current password" auto="current-password" value={f.current} onChange={(current) => setF({ ...f, current })} />
      <Field label={`New password (min ${MIN_PASSWORD_LEN})`} auto="new-password" value={f.next} onChange={(next) => setF({ ...f, next })} />
      <Field label="Confirm new password" auto="new-password" value={f.confirm} onChange={(confirm) => setF({ ...f, confirm })} />
      {error && <p role="alert" className="text-xs text-negative">{error}</p>}
      <button type="submit" disabled={busy} className="w-full py-2 rounded-interactive bg-ink text-paper text-sm font-semibold disabled:opacity-50">
        {busy ? 'Saving…' : 'Change password'}
      </button>
    </form>
  );
};
