import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { translations, defaultLanguage, supportedLanguages } from '../i18n/translations'
import { db } from '../services/db'
import api from '../services/api'
import { createCurrencyFormatter, currencySymbol } from '../utils/currencyFormat'

const LanguageContext = createContext(null)

// A signed-out page has no profile to ask, so it shows the language's usual currency.
const LANGUAGE_CURRENCY_CODES = { en: 'GBP', ro: 'RON', es: 'EUR' }

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

/** Everything that depends on which currency amounts default to. */
function useCurrencyValues(currencyCode, language, unknownCurrencyLabel, exchangeRates) {
  const symbolFor = useCallback((code) => currencySymbol(code || currencyCode, language), [currencyCode, language])
  const currency = useMemo(() => ({ code: currencyCode, symbol: symbolFor(currencyCode) }), [currencyCode, symbolFor])

  // Convert an amount from EUR to the active currency using live rates
  const convertFromEur = useCallback((amountEur) => {
    if (!exchangeRates || currencyCode === 'EUR') return amountEur
    const rate = exchangeRates[currencyCode]
    return rate ? amountEur * rate : amountEur
  }, [exchangeRates, currencyCode])

  const formatCurrency = useMemo(
    () => createCurrencyFormatter({ language, currency: currencyCode, unknownCurrencyLabel }),
    [language, currencyCode, unknownCurrencyLabel],
  )

  return useMemo(
    () => ({ currency, symbolFor, convertFromEur, formatCurrency }),
    [currency, symbolFor, convertFromEur, formatCurrency],
  )
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(defaultLanguage)
  const [isLoaded, setIsLoaded] = useState(false)
  // Live exchange rates keyed by currency code (EUR base)
  const [exchangeRates, setExchangeRates] = useState(null)
  const ratesFetchedRef = useRef(false)
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

  // Fetch live exchange rates from backend once per session (after login)
  useEffect(() => {
    if (ratesFetchedRef.current || !localStorage.getItem('auth_session')) return
    ratesFetchedRef.current = true
    api.get('/external/currency-rates')
      .then((res) => {
        if (res.data?.rates) {
          setExchangeRates(res.data.rates)
        }
      })
      .catch(() => {/* silently ignore — fallback rates are baked into the backend */})
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
  
  const languageCurrencyCode = LANGUAGE_CURRENCY_CODES[language] || LANGUAGE_CURRENCY_CODES[defaultLanguage]
  const currencyValues = useCurrencyValues(languageCurrencyCode, language, t('financial.unknownCurrency'), exchangeRates)

  const value = {
    language,
    setLanguage,
    loadLanguageFromUser,
    t,
    isLoaded,
    supportedLanguages,
    ...currencyValues,
    exchangeRates,
    languageNames,
  }

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  )
}

/**
 * Below this, amounts default to the currency the person chose in their profile. Neither their
 * location nor their language overrides it. Without a choice (signed out) the language's stays.
 */
export function AccountCurrencyScope({ currencyCode, children }) {
  const inherited = useLanguage()
  const accountValues = useCurrencyValues(
    currencyCode || inherited.currency.code, inherited.language,
    inherited.t('financial.unknownCurrency'), inherited.exchangeRates,
  )
  const value = useMemo(() => ({ ...inherited, ...accountValues }), [inherited, accountValues])
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
  const { currency, formatCurrency, convertFromEur, exchangeRates, symbolFor, language } = useLanguage()
  return { currency, formatCurrency, convertFromEur, exchangeRates, symbolFor, language }
}
