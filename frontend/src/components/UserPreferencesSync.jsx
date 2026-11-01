/**
 * UserPreferencesSync - Synchronizes user preferences between backend and context providers
 * 
 * This component runs inside the AuthProvider and syncs user preferences (theme, language)
 * from the backend to the local context providers when user data is loaded.
 */
import { useEffect, useRef } from 'react'
import { DateFormatProvider } from '../contexts/DateFormatContext'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'
import { useLanguage } from '../contexts/LanguageContext'

export default function UserPreferencesSync({ children }) {
  const { user, isAuthenticated } = useAuth()
  const { loadThemeFromUser } = useTheme()
  const { language, isLoaded, loadLanguageFromUser } = useLanguage()
  const lastSyncedPreferences = useRef(null)
  
  // Sync preferences when user logs in or user data changes
  useEffect(() => {
    // Apply the profile after local preference loading, so a stale local read cannot override it.
    if (isAuthenticated && user && isLoaded) {
      const previous = lastSyncedPreferences.current
      // Sync theme from user data
      if (user.theme && previous?.id !== user.id) {
        loadThemeFromUser(user)
      }
      
      // Sync language from user data
      if (user.language && (previous?.id !== user.id || previous?.language !== user.language)) {
        loadLanguageFromUser(user)
      }
      
      lastSyncedPreferences.current = { id: user.id, language: user.language }
    }
    
    // Reset when logged out
    if (!isAuthenticated) {
      lastSyncedPreferences.current = null
    }
  }, [user, isAuthenticated, isLoaded, loadThemeFromUser, loadLanguageFromUser])
  
  const preferences = isAuthenticated ? user : null
  return <DateFormatProvider language={language} dateFormat={preferences?.date_format} timezone={preferences?.timezone}>
    {children}
  </DateFormatProvider>
}
