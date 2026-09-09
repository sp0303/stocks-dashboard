import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App.jsx'
import Screener from './components/Screener.jsx'
import Orb from './pages/Orb.jsx'
import './styles.css'

// Standalone pages get real paths. Everything else falls through to the persona-based
// dashboard, which keeps its own state in query params (?persona=, ?clientId=) — so
// existing links keep working unchanged.
//
// A path route needs the server to serve index.html for unknown paths. Vite's dev
// server already does; in production see frontend/DEPLOY.md for the one nginx line.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/screener" element={<Screener />} />
        <Route path="/orb" element={<Orb />} />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
