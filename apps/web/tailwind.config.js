/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: 'var(--canvas, #fbfbfb)',
        paper: 'var(--paper, #ffffff)',
        ink: 'var(--ink, #111827)',
        subtle: 'var(--subtle, #6b7280)',
        hairline: 'var(--hairline, #e5e7eb)',
        accent: {
          DEFAULT: 'var(--accent, #0f172a)',
          foreground: '#ffffff',
        },
        positive: 'var(--positive, #16a34a)',
        negative: 'var(--negative, #dc2626)',
      },
      borderRadius: {
        card: '24px',
        interactive: '18px',
      },
    },
  },
  plugins: [],
}
