import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import Screener from './components/Screener.jsx'
import './styles.css'

// Standalone route: /screener renders its own page, deliberately NOT linked into the
// main persona-based dashboard UI. Everything else falls through to the normal App.
const isScreener = window.location.pathname.replace(/\/+$/, '') === '/screener'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isScreener ? <Screener /> : <App />}
  </React.StrictMode>,
)
