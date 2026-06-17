import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { LanguageProvider } from './contexts/LanguageContext'
import { ConfirmProvider } from './components/ui/ConfirmDialog'
import UserPreferencesSync from './components/UserPreferencesSync'

// Remove initial loader
document.body.classList.add('app-loaded')

// Stale app-shell recovery.
// Every route is code-split via React.lazy(), so after a new deploy an open tab
// running the previous shell can try to import a hashed chunk that no longer
// exists on the server — leaving the user stranded on a blank route. Vite emits
// `vite:preloadError` for exactly this. Reload once to pick up the fresh shell
// (the no-store sw.js + precache serve the new assets). A short sessionStorage
// cooldown prevents a reload loop if the chunk is genuinely unrecoverable.
window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  const RELOAD_KEY = 'gc_chunk_reload_at'
  const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0)
  if (Date.now() - last < 10000) return // already retried very recently — don't loop
  sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
  window.location.reload()
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <LanguageProvider>
          <ConfirmProvider>
            <AuthProvider>
              <UserPreferencesSync>
                <App />
              </UserPreferencesSync>
            </AuthProvider>
          </ConfirmProvider>
        </LanguageProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
