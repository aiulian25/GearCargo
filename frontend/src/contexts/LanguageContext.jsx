import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { translations, defaultLanguage, supportedLanguages } from '../i18n/translations'
import { db } from '../services/db'
import api from '../services/api'

const LanguageContext = createContext(null)

// Language to Currency mapping
const languageCurrencyMap = {
  en: { code: 'GBP', symbol: '£', name: 'British Pound' },
  ro: { code: 'RON', symbol: 'lei', name: 'Romanian Leu' },
  es: { code: 'EUR', symbol: '€', name: 'Euro' },
}

// Language display names (in their native language)
const languageNames = {
  en: { native: 'English', flag: '🇬🇧' },
  ro: { native: 'Română', flag: '🇷🇴' },
  es: { native: 'Español', flag: '🇪🇸' },
}

// Helper to get nested translation value
function getNestedValue(obj, path) {
  return path.split('.').reduce((current, key) => current?.[key], obj)
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(defaultLanguage)
  const [isLoaded, setIsLoaded] = useState(false)
  
  // Load saved language preference
  useEffect(() => {
    const loadLanguage = async () => {
      try {
        // Check localStorage first
        const savedLang = localStorage.getItem('language')
        if (savedLang && supportedLanguages.includes(savedLang)) {
          setLanguageState(savedLang)
        } else {
          // Try to get from IndexedDB
          const dbLang = await db.settings.get('language')
          if (dbLang && supportedLanguages.includes(dbLang.value)) {
            setLanguageState(dbLang.value)
          } else {
            // Try to detect from browser
            const browserLang = navigator.language?.split('-')[0]
            if (supportedLanguages.includes(browserLang)) {
              setLanguageState(browserLang)
            }
          }
        }
      } catch (error) {
        console.warn('Failed to load language preference:', error)
      } finally {
        setIsLoaded(true)
      }
    }
    
    loadLanguage()
  }, [])
  
  // Set language and persist
  const setLanguage = useCallback(async (lang) => {
    if (!supportedLanguages.includes(lang)) {
      console.warn(`Language ${lang} not supported`)
      return
    }
    
    setLanguageState(lang)
    localStorage.setItem('language', lang)
    
    try {
      await db.settings.put({ key: 'language', value: lang })
    } catch (error) {
      console.warn('Failed to save language to DB:', error)
    }
    
    // Sync to backend if authenticated (S05 — check non-secret flag, not token)
    if (localStorage.getItem('auth_session')) {
      try {
        await api.put('/auth/me', { language: lang })
      } catch (error) {
        console.warn('Failed to sync language to server:', error)
      }
    }
    
    // Update HTML lang attribute
    document.documentElement.lang = lang
  }, [])
  
  // Load language from user data (called by AuthContext on login)
  const loadLanguageFromUser = useCallback((userData) => {
    if (userData?.language && supportedLanguages.includes(userData.language)) {
      setLanguageState(userData.language)
      localStorage.setItem('language', userData.language)
      document.documentElement.lang = userData.language
    }
  }, [])
  
  // Translation function
  const t = useCallback((key, params = {}) => {
    const inCurrentLang = getNestedValue(translations[language], key)
    const inDefaultLang = getNestedValue(translations[defaultLanguage], key)
    const translation = inCurrentLang || inDefaultLang || key

    // I12: Warn in dev mode when a key is missing from ALL locales so missing
    // translations are surfaced immediately rather than silently falling through
    // to the hardcoded || 'English fallback' pattern in JSX.
    if (import.meta.env.DEV && !inCurrentLang && !inDefaultLang) {
      console.warn(`[i18n] Missing translation key: "${key}"`)
    }

    // Replace params like {name} with actual values
    if (typeof translation === 'string' && Object.keys(params).length > 0) {
      return Object.entries(params).reduce(
        (str, [key, value]) => str.replace(new RegExp(`{${key}}`, 'g'), value),
        translation
      )
    }
    
    return translation
  }, [language])
  
  // Get current currency based on language
  const currency = languageCurrencyMap[language] || languageCurrencyMap[defaultLanguage]
  
  // Format currency helper
  const formatCurrency = useCallback((amount, options = {}) => {
    const { showSymbol = true, decimals = 2 } = options
    const formattedAmount = Number(amount).toFixed(decimals)
    
    if (currency.code === 'RON') {
      // Romanian format: 123.45 lei
      return showSymbol ? `${formattedAmount} ${currency.symbol}` : formattedAmount
    }
    // Other currencies: £123.45 or €123.45
    return showSymbol ? `${currency.symbol}${formattedAmount}` : formattedAmount
  }, [currency])
  
  const value = {
    language,
    setLanguage,
    loadLanguageFromUser,
    t,
    isLoaded,
    supportedLanguages,
    currency,
    formatCurrency,
    languageNames,
  }
  
  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider')
  }
  return context
}

// Hook for quick translations
export function useTranslation() {
  const { t, language } = useLanguage()
  return { t, language }
}

// Hook for currency
export function useCurrency() {
  const { currency, formatCurrency, language } = useLanguage()
  return { currency, formatCurrency, language }
}
