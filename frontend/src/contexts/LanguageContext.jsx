import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { translations, defaultLanguage, supportedLanguages } from '../i18n/translations'
import { db } from '../services/db'
import api from '../services/api'

const LanguageContext = createContext(null)

// Language to Currency mapping (fallback when location is unavailable)
const languageCurrencyMap = {
  en: { code: 'GBP', symbol: '£', name: 'British Pound' },
  ro: { code: 'RON', symbol: 'lei', name: 'Romanian Leu' },
  es: { code: 'EUR', symbol: '€', name: 'Euro' },
}

// Country ISO code → currency (covers all EU + common countries)
const countryCurrencyMap = {
  // Euro zone
  AT: { code: 'EUR', symbol: '€', name: 'Euro' },
  BE: { code: 'EUR', symbol: '€', name: 'Euro' },
  CY: { code: 'EUR', symbol: '€', name: 'Euro' },
  DE: { code: 'EUR', symbol: '€', name: 'Euro' },
  EE: { code: 'EUR', symbol: '€', name: 'Euro' },
  ES: { code: 'EUR', symbol: '€', name: 'Euro' },
  FI: { code: 'EUR', symbol: '€', name: 'Euro' },
  FR: { code: 'EUR', symbol: '€', name: 'Euro' },
  GR: { code: 'EUR', symbol: '€', name: 'Euro' },
  HR: { code: 'EUR', symbol: '€', name: 'Euro' },
  IE: { code: 'EUR', symbol: '€', name: 'Euro' },
  IT: { code: 'EUR', symbol: '€', name: 'Euro' },
  LT: { code: 'EUR', symbol: '€', name: 'Euro' },
  LU: { code: 'EUR', symbol: '€', name: 'Euro' },
  LV: { code: 'EUR', symbol: '€', name: 'Euro' },
  MT: { code: 'EUR', symbol: '€', name: 'Euro' },
  NL: { code: 'EUR', symbol: '€', name: 'Euro' },
  PT: { code: 'EUR', symbol: '€', name: 'Euro' },
  SI: { code: 'EUR', symbol: '€', name: 'Euro' },
  SK: { code: 'EUR', symbol: '€', name: 'Euro' },
  // Non-euro EU + common European countries
  BG: { code: 'BGN', symbol: 'лв', name: 'Bulgarian Lev' },
  CH: { code: 'CHF', symbol: 'CHF', name: 'Swiss Franc' },
  CZ: { code: 'CZK', symbol: 'Kč', name: 'Czech Koruna' },
  DK: { code: 'DKK', symbol: 'kr', name: 'Danish Krone' },
  GB: { code: 'GBP', symbol: '£', name: 'British Pound' },
  UK: { code: 'GBP', symbol: '£', name: 'British Pound' },
  HU: { code: 'HUF', symbol: 'Ft', name: 'Hungarian Forint' },
  NO: { code: 'NOK', symbol: 'kr', name: 'Norwegian Krone' },
  PL: { code: 'PLN', symbol: 'zł', name: 'Polish Złoty' },
  RO: { code: 'RON', symbol: 'lei', name: 'Romanian Leu' },
  SE: { code: 'SEK', symbol: 'kr', name: 'Swedish Krona' },
  // Other major countries
  US: { code: 'USD', symbol: '$', name: 'US Dollar' },
  CA: { code: 'CAD', symbol: 'CA$', name: 'Canadian Dollar' },
  AU: { code: 'AUD', symbol: 'A$', name: 'Australian Dollar' },
  JP: { code: 'JPY', symbol: '¥', name: 'Japanese Yen' },
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
  // Location-detected currency overrides the language-based default
  const [locationCurrency, setLocationCurrency] = useState(null)
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

  // Set currency from detected country code (called by Dashboard after geolocation)
  const setCurrencyFromCountry = useCallback((countryCode) => {
    if (!countryCode) return
    const cc = countryCode.toUpperCase()
    const found = countryCurrencyMap[cc]
    if (found) {
      setLocationCurrency(found)
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
  
  // Active currency: location-detected wins over language default
  const currency = locationCurrency || languageCurrencyMap[language] || languageCurrencyMap[defaultLanguage]

  // Convert an amount from EUR to the active currency using live rates
  const convertFromEur = useCallback((amountEur) => {
    if (!exchangeRates || currency.code === 'EUR') return amountEur
    const rate = exchangeRates[currency.code]
    return rate ? amountEur * rate : amountEur
  }, [exchangeRates, currency.code])

  // Format currency helper
  const formatCurrency = useCallback((amount, options = {}) => {
    const { showSymbol = true, decimals = 2 } = options
    const formattedAmount = Number(amount).toFixed(decimals)

    // Currencies that follow the number (suffix format)
    const suffixCodes = new Set(['RON', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'CHF', 'BGN', 'kr', 'lei', 'Ft', 'Kč', 'zł', 'лв'])
    if (suffixCodes.has(currency.code) || suffixCodes.has(currency.symbol)) {
      return showSymbol ? `${formattedAmount} ${currency.symbol}` : formattedAmount
    }
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
    convertFromEur,
    exchangeRates,
    setCurrencyFromCountry,
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
  const { currency, formatCurrency, convertFromEur, exchangeRates, setCurrencyFromCountry, language } = useLanguage()
  return { currency, formatCurrency, convertFromEur, exchangeRates, setCurrencyFromCountry, language }
}
