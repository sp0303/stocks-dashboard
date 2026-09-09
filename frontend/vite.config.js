import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base '/' (not './') because the app now has real path routes: from /orb, relative
// asset paths would resolve to /orb/assets/… and 404. The server must also serve
// index.html for unknown paths — see DEPLOY.md.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    port: 5180,
    host: true, // bind 0.0.0.0 so the Cloudflare tunnel can reach the dev server
    allowedHosts: ['stocks.sharatpatnayakuni.site', '.sharatpatnayakuni.site'],
    proxy: {
      // dev/prod proxy → backend runs on the same host, port 8010
      '/api': 'http://127.0.0.1:8010',
    },
  },
})
