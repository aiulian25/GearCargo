import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { db } from '../services/db'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  
  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token')
      
      if (!token) {
        setIsLoading(false)
        return
      }
      
      try {
        const response = await api.get('/auth/me')
        setUser(response.data)
        setIsAuthenticated(true)
        
        // Cache user data offline
        await db.settings.put({ key: 'user', value: response.data })
      } catch (error) {
        // Try to get cached user data
        const cachedUser = await db.settings.get('user')
        if (cachedUser) {
          setUser(cachedUser.value)
          setIsAuthenticated(true)
        } else {
          // Token invalid, clear storage
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
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
    
    const { access_token, refresh_token, user: userData } = response.data
    
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    
    setUser(userData)
    setIsAuthenticated(true)
    
    // Cache user data
    await db.settings.put({ key: 'user', value: userData })
    
    return { success: true }
  }, [])
  
  const register = useCallback(async (data) => {
    const response = await api.post('/auth/register', data)
    
    const { access_token, refresh_token, user: userData } = response.data
    
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    
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
      // Ignore logout errors
    }
    
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    
    // Clear cached data
    await db.settings.delete('user')
    
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
  
  const refreshToken = useCallback(async () => {
    const refresh = localStorage.getItem('refresh_token')
    
    if (!refresh) {
      throw new Error('No refresh token')
    }
    
    const response = await api.post('/auth/refresh', {
      refresh_token: refresh,
    })
    
    localStorage.setItem('access_token', response.data.access_token)
    localStorage.setItem('refresh_token', response.data.refresh_token)
    
    return response.data.access_token
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
