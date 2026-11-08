/** Light/dark theme: follows the system setting until the viewer picks one (a per-viewer convenience, not state). */
export type Theme = 'light' | 'dark';
const KEY = 'pi_theme';

function stored(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null; // storage blocked: fall back to the system setting
  }
}

export function currentTheme(): Theme {
  return stored() ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* ignore: the choice just won't persist */
  }
  applyTheme(theme);
}

/** Call once before the first render so there is no light flash. */
export function initTheme(): void {
  applyTheme(currentTheme());
}
