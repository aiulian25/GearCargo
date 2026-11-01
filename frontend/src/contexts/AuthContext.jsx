import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { migratePrivateStorage, readPrivateProfile, savePrivateProfile, privateSessionValid, clearPrivatePageStorage } from '../utils/privateStorage'
import { getQueueState } from '../db/mutationQueue'
import { beginIdentityTransition, establishOfflineIdentity, restoreOfflineIdentity, forgetBoundIdentity, getBoundIdentity } from '../utils/offlineIdentity'

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
    let cancelled = false
    const onIdentitySuspended = async event => {
      if (event.type === 'message' && event.data?.type !== 'OFFLINE_IDENTITY_SUSPENDED') return
      if (event.type === 'storage' && event.key !== 'gearcargo_identity_boundary') return
      const revision = event.data?.revision || event.detail?.revision || event.newValue
      if (revision && (await getQueueState()).revision !== revision) return
      cancelled = true
      clearPrivatePageStorage()
      forgetBoundIdentity()
      setUser(null)
      setIsAuthenticated(false)
      setIsLoading(false)
    }
    navigator.serviceWorker?.addEventListener('message', onIdentitySuspended)
    window.addEventListener('private-identity-suspended', onIdentitySuspended)
    window.addEventListener('storage', onIdentitySuspended)
    const checkLifetime = async () => {
      const state = await getQueueState()
      if (state.identity && !privateSessionValid(state)) await beginIdentityTransition({ expectedRevision: state.revision })
    }
    const lifetimeTimer = setInterval(() => { checkLifetime().catch(() => { forgetBoundIdentity(); setUser(null); setIsAuthenticated(false) }) }, 30000)
    const checkAuth = async () => {
      let attemptRevision
      try {
        await migratePrivateStorage()
        attemptRevision = (await getQueueState()).revision
        const response = await api.get('/auth/me')
        if (cancelled) return
        await establishOfflineIdentity(response.data.id)
        if (cancelled) return
        await savePrivateProfile(response.data, getBoundIdentity())
        if (cancelled) return
        setUser(response.data)
        setIsAuthenticated(true)
        localStorage.setItem('auth_session', '1')

        // The profile and its identity revision were saved atomically above.
      } catch (error) {
        // Try to get cached user data for offline support
        const cachedUser = await readPrivateProfile()
        if (!cancelled && cachedUser && !error.response && attemptRevision === (await getQueueState()).revision
            && await restoreOfflineIdentity(cachedUser.value.id)) {
          // Offline — surface cached profile, auth state uncertain
          setUser(cachedUser.value)
          setIsAuthenticated(true)
        } else {
          // Online 401 or network error — not authenticated
          localStorage.removeItem('auth_session')
          if (!cancelled) await checkLifetime()
        }
      } finally {
        setIsLoading(false)
      }
    }
    
    checkAuth()
    return () => {
      cancelled = true
      navigator.serviceWorker?.removeEventListener('message', onIdentitySuspended)
      window.removeEventListener('private-identity-suspended', onIdentitySuspended)
      window.removeEventListener('storage', onIdentitySuspended)
      clearInterval(lifetimeTimer)
    }
  }, [])
  
  const login = useCallback(async (email, password, totpCode = null, remember = false, backupCode = null) => {
    const transition = await beginIdentityTransition()
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
    await establishOfflineIdentity(userData.id, transition.revision)

    await savePrivateProfile(userData, getBoundIdentity())

    localStorage.setItem('auth_session', '1')
    setUser(userData)
    setIsAuthenticated(true)
    
    // Private profile was stored before exposing the authenticated UI.
    
    return { success: true }
  }, [])
  
  // A passkey verifies the person on the device, so it satisfies both steps and
  // never returns requires_2fa. Everything after the response matches `login`:
  // the identity transition has to happen for a passkey sign-in too, or queued
  // offline work and private cached data would stay bound to the previous one.
  const loginWithPasskey = useCallback(async () => {
    const { startAuthentication } = await import('@simplewebauthn/browser')
    const { data: options } = await api.post('/auth/passkeys/login/options')
    const credential = await startAuthentication({ optionsJSON: options })

    const transition = await beginIdentityTransition()
    const response = await api.post('/auth/passkeys/login', { credential })

    const { user: userData } = response.data
    await establishOfflineIdentity(userData.id, transition.revision)

    await savePrivateProfile(userData, getBoundIdentity())

    localStorage.setItem('auth_session', '1')
    setUser(userData)
    setIsAuthenticated(true)

    return { success: true }
  }, [])

  const register = useCallback(async (data) => {
    const transition = await beginIdentityTransition()
    const response = await api.post('/auth/register', data)
    
    // S05 — tokens delivered via cookies only.
    const { user: userData } = response.data
    await establishOfflineIdentity(userData.id, transition.revision)

    await savePrivateProfile(userData, getBoundIdentity())

    localStorage.setItem('auth_session', '1')
    setUser(userData)
    setIsAuthenticated(true)
    
    // Private profile was stored before exposing the authenticated UI.
    
    return { success: true }
  }, [])
  
  const logout = useCallback(async () => {
    const transition = await beginIdentityTransition({ logout: true })
    try {
      if (transition) await api.post('/auth/logout')
    } catch (error) {
      // Ignore logout errors — server clears cookies regardless
    }

    // beginIdentityTransition acknowledged cleanup before the logout request.

    // S05 — cookies are expired by the server response; clear local state last.
    forgetBoundIdentity()
    setUser(null)
    setIsAuthenticated(false)
  }, [])
  
  const updateUser = useCallback(async (data) => {
    const identity = getBoundIdentity()
    const response = await api.put('/auth/me', data)
    await savePrivateProfile(response.data.user, identity)
    setUser(response.data.user)
    return response.data.user
  }, [])
  
  const refreshUser = useCallback(async () => {
    try {
      const identity = getBoundIdentity()
      const response = await api.get('/auth/me')
      await savePrivateProfile(response.data, identity)
      setUser(response.data)
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
    loginWithPasskey,
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
