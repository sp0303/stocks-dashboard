/**
 * LoginPage — full-page login form.
 * Four states: idle, loading, error, success (redirects).
 * Complies with AGENTS.md §5.12 (four async states) and §5.13 (accessible).
 */

import { useState } from 'react';
import { Database } from 'lucide-react';
import { apiLogin } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';

interface Props {
  onLoginSuccess: (refreshToken: string) => void;
}

export function LoginPage({ onLoginSuccess }: Props) {
  const setToken = useAuthStore((s) => s.setToken);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiLogin(email, password);
      setToken(data.access_token, data.expires_in);
      // Store refresh token in sessionStorage (dev fallback; prod uses httpOnly cookie)
      sessionStorage.setItem('pi_rt', data.refresh_token);
      onLoginSuccess(data.refresh_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center bg-canvas px-4"
      role="main"
      aria-label="Login page"
    >
      {/* Logo */}
      <div className="mb-8 flex flex-col items-center gap-3">
        <div className="w-14 h-14 rounded-2xl bg-ink text-paper flex items-center justify-center font-bold text-xl shadow-lg">
          PI
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-ink">Portfolio Intelligence</h1>
        <p className="text-sm text-subtle">v2 Engine · Sign in to continue</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm bg-paper border border-hairline rounded-2xl p-8 shadow-sm">
        <form onSubmit={handleSubmit} noValidate aria-label="Login form">
          {/* Email */}
          <div className="mb-5">
            <label
              htmlFor="email"
              className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1.5"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              className="w-full px-3.5 py-2.5 rounded-lg border border-hairline bg-canvas text-ink text-sm
                         placeholder:text-subtle/60 focus:outline-none focus:ring-2 focus:ring-ink/20
                         disabled:opacity-50"
              placeholder="you@example.com"
              aria-describedby={error ? 'login-error' : undefined}
            />
          </div>

          {/* Password */}
          <div className="mb-6">
            <label
              htmlFor="password"
              className="block text-xs font-semibold uppercase tracking-wider text-subtle mb-1.5"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              className="w-full px-3.5 py-2.5 rounded-lg border border-hairline bg-canvas text-ink text-sm
                         placeholder:text-subtle/60 focus:outline-none focus:ring-2 focus:ring-ink/20
                         disabled:opacity-50"
              placeholder="••••••••"
            />
          </div>

          {/* Error */}
          {error && (
            <p
              id="login-error"
              role="alert"
              aria-live="assertive"
              className="mb-4 text-sm text-ember font-medium text-center"
            >
              {error}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !email || !password}
            className="w-full py-2.5 rounded-xl bg-ink text-paper text-sm font-semibold
                       hover:bg-ink/90 active:scale-[0.98] transition-all
                       disabled:opacity-40 disabled:cursor-not-allowed
                       focus:outline-none focus:ring-2 focus:ring-ink/30"
            aria-busy={loading}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span
                  className="w-4 h-4 rounded-full border-2 border-paper/40 border-t-paper animate-spin"
                  aria-hidden="true"
                />
                Signing in…
              </span>
            ) : (
              'Sign in'
            )}
          </button>
        </form>
      </div>

      {/* Footer */}
      <p className="mt-8 text-xs text-subtle flex items-center gap-1.5">
        <Database className="w-3.5 h-3.5" aria-hidden="true" />
        Connected to PostgreSQL 16 · Strictly typed v2 engine
      </p>
    </div>
  );
}
