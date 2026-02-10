/**
 * UserPreferencesSync - Synchronizes user preferences between backend and context providers
 * 
 * This component runs inside the AuthProvider and syncs user preferences (theme, language)
 * from the backend to the local context providers when user data is loaded.
 */
import { useEffect, useRef } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'
import { useLanguage } from '../contexts/LanguageContext'

export default function UserPreferencesSync({ children }) {
  const { user, isAuthenticated } = useAuth()
  const { loadThemeFromUser } = useTheme()
  const { loadLanguageFromUser } = useLanguage()
  const lastSyncedUserId = useRef(null)
  
  // Sync preferences when user logs in or user data changes
  useEffect(() => {
    if (isAuthenticated && user && user.id !== lastSyncedUserId.current) {
      // Sync theme from user data
      if (user.theme) {
        loadThemeFromUser(user)
      }
      
      // Sync language from user data
      if (user.language) {
        loadLanguageFromUser(user)
      }
      
      lastSyncedUserId.current = user.id
    }
    
    // Reset when logged out
    if (!isAuthenticated) {
      lastSyncedUserId.current = null
    }
  }, [user, isAuthenticated, loadThemeFromUser, loadLanguageFromUser])
  
  return children
}
