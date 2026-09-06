import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' keeps asset paths relative so the build also works on GitHub Pages.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5180,
    host: true, // bind 0.0.0.0 so the Cloudflare tunnel can reach the dev server
    allowedHosts: ['stocks.sharatpatnayakuni.site', '.sharatpatnayakuni.site'],
    proxy: {
      // still available for local dev if VITE_API_BASE is unset
      '/api': 'http://127.0.0.1:8011',
    },
  },
})
