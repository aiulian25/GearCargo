import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { LanguageProvider } from './contexts/LanguageContext'
import UserPreferencesSync from './components/UserPreferencesSync'
import { registerSW } from 'virtual:pwa-register'

// Register service worker
const updateSW = registerSW({
  onNeedRefresh() {
    // Automatically update without asking
    console.log('New version available, updating...')
    updateSW(true)
  },
  onOfflineReady() {
    console.log('App ready for offline use')
  },
  immediate: true, // Register immediately
})

// Remove initial loader
document.body.classList.add('app-loaded')

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <LanguageProvider>
          <AuthProvider>
            <UserPreferencesSync>
              <App />
            </UserPreferencesSync>
          </AuthProvider>
        </LanguageProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
