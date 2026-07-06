import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { db } from '../services/db'
import { clearApiCache } from '../utils/swCache'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  
  // Check authentication on mount.
  // S05 — tokens are httpOnly cookies; we cannot read them in JS.
  // Instead we call /auth/me and let the browser send the cookie automatically.
  // A 401 means "not authenticated" — no token to clear.
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await api.get('/auth/me')
        setUser(response.data)
        setIsAuthenticated(true)
        localStorage.setItem('auth_session', '1')

        // Cache user data offline
        await db.settings.put({ key: 'user', value: response.data })
      } catch (error) {
        // Try to get cached user data for offline support
        const cachedUser = await db.settings.get('user')
        if (cachedUser && navigator.onLine === false) {
          // Offline — surface cached profile, auth state uncertain
          setUser(cachedUser.value)
          setIsAuthenticated(true)
        } else {
          // Online 401 or network error — not authenticated
          localStorage.removeItem('auth_session')
        }
      } finally {
        setIsLoading(false)
      }
    }
    
    checkAuth()
  }, [])
  
  const login = useCallback(async (email, password, totpCode = null, remember = false, backupCode = null) => {
    const response = await api.post('/auth/login', {
      email,
      password,
      totp_code: totpCode,
      backup_code: backupCode,
    })
    
    if (response.data.requires_2fa) {
      return { requires2FA: true }
    }
    
    // S05 — tokens are set as httpOnly cookies by the server.
    // We only read the user profile from the JSON response.
    const { user: userData } = response.data

    // Purge any API cache left by a previous account on this device so the
    // newly signed-in user can never read stale/foreign data offline.
    await clearApiCache()

    localStorage.setItem('auth_session', '1')
    setUser(userData)
    setIsAuthenticated(true)
    
    // Cache user data
    await db.settings.put({ key: 'user', value: userData })
    
    return { success: true }
  }, [])
  
  const register = useCallback(async (data) => {
    const response = await api.post('/auth/register', data)
    
    // S05 — tokens delivered via cookies only.
    const { user: userData } = response.data

    await clearApiCache()

    localStorage.setItem('auth_session', '1')
    setUser(userData)
    setIsAuthenticated(true)
    
    // Cache user data
    await db.settings.put({ key: 'user', value: userData })
    
    return { success: true }
  }, [])
  
  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch (error) {
      // Ignore logout errors — server clears cookies regardless
    }

    // SEC-06: purge all per-user cached data BEFORE we clear the session flag /
    // auth state, so "signed out" always implies "no personal data left at rest"
    // (Dexie user record + the SW api-cache/media-cache) on a shared device.
    await db.settings.delete('user')
    await clearApiCache()

    // S05 — cookies are expired by the server response; clear local state last.
    localStorage.removeItem('auth_session')
    setUser(null)
    setIsAuthenticated(false)
  }, [])
  
  const updateUser = useCallback(async (data) => {
    const response = await api.put('/auth/me', data)
    setUser(response.data.user)
    await db.settings.put({ key: 'user', value: response.data.user })
    return response.data.user
  }, [])
  
  const refreshUser = useCallback(async () => {
    try {
      const response = await api.get('/auth/me')
      setUser(response.data)
      await db.settings.put({ key: 'user', value: response.data })
      return response.data
    } catch (error) {
      console.error('Failed to refresh user:', error)
      return null
    }
  }, [])

  // S05 — token refresh is handled transparently by api.js interceptor via
  // the httpOnly refresh_token cookie.  This stub is kept for API compatibility
  // but callers no longer need to invoke it manually.
  const refreshToken = useCallback(async () => {
    await api.post('/auth/refresh', {})
  }, [])
  
  const value = {
    user,
    isLoading,
    isAuthenticated,
    login,
    register,
    logout,
    updateUser,
    refreshUser,
    refreshToken,
  }
  
  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
