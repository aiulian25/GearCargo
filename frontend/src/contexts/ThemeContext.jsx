import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { db } from '../services/db'

const ThemeContext = createContext(null)

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    // Check localStorage first, then system preference
    const saved = localStorage.getItem('theme')
    if (saved) return saved
    
    if (window.matchMedia('(prefers-color-scheme: light)').matches) {
      return 'light'
    }
    return 'dark' // Default to dark
  })
  
  useEffect(() => {
    const root = document.documentElement
    
    if (theme === 'light') {
      root.classList.add('light')
      root.classList.remove('dark')
    } else {
      root.classList.add('dark')
      root.classList.remove('light')
    }
    
    // Update theme-color meta tag
    const themeColor = theme === 'light' ? '#f8fafc' : '#1e293b'
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColor)
    
    localStorage.setItem('theme', theme)
  }, [theme])
  
  // Set theme and sync to backend
  const setTheme = useCallback(async (newTheme) => {
    setThemeState(newTheme)
    localStorage.setItem('theme', newTheme)
    
    // Save to IndexedDB for offline support
    try {
      await db.settings.put({ key: 'theme', value: newTheme })
    } catch (error) {
      console.warn('Failed to save theme to IndexedDB:', error)
    }
    
    // Sync to backend if authenticated (S05 — check non-secret flag, not token)
    if (localStorage.getItem('auth_session')) {
      try {
        await api.put('/auth/me', { theme: newTheme })
      } catch (error) {
        console.warn('Failed to sync theme to server:', error)
      }
    }
  }, [])
  
  // Load theme from user data (called by AuthContext on login)
  const loadThemeFromUser = useCallback((userData) => {
    if (userData?.theme) {
      setThemeState(userData.theme)
      localStorage.setItem('theme', userData.theme)
    }
  }, [])
  
  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(newTheme)
  }, [theme, setTheme])
  
  const value = {
    theme,
    setTheme,
    toggleTheme,
    loadThemeFromUser,
    isDark: theme === 'dark',
    isLight: theme === 'light',
  }
  
  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
