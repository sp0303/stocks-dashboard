import React, { useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { currentTheme, saveTheme, type Theme } from '@/lib/theme';

/** Header button that switches between light and dark. */
export const ThemeToggle: React.FC = () => {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      onClick={() => {
        saveTheme(next);
        setTheme(next);
      }}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-canvas border border-hairline hover:bg-paper text-xs transition-colors"
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
    >
      {theme === 'dark' ? <Sun className="w-3.5 h-3.5" aria-hidden /> : <Moon className="w-3.5 h-3.5" aria-hidden />}
    </button>
  );
};
