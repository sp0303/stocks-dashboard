import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './styles.css'

// Route-level code splitting: the dashboard, the screener and the ORB page are each big
// and rarely used together, so they load as separate chunks on demand instead of one
// ~830 KB bundle up front. This is the single biggest win on first-load time.
const App = lazy(() => import('./App.jsx'))
const Screener = lazy(() => import('./components/Screener.jsx'))
const Orb = lazy(() => import('./pages/Orb.jsx'))

const Splash = () => (
  <div style={{ padding: 40, textAlign: 'center', color: 'var(--muted, #888)' }}>Loading…</div>
)

// A path route needs the server to serve index.html for unknown paths. Vite's dev server
// already does; in production see frontend/DEPLOY.md for the one nginx line.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Suspense fallback={<Splash />}>
        <Routes>
          <Route path="/screener" element={<Screener />} />
          <Route path="/orb" element={<Orb />} />
          <Route path="*" element={<App />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  </React.StrictMode>,
)
