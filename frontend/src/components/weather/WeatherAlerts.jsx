/**
 * GearCargo - Weather Driving Alerts Component (PWA)
 * Displays weather-based driving safety alerts and tips
 */

import { useState, useEffect, useCallback } from 'react'
import { externalApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

// Alert Icons as SVG components
const AlertIcons = {
  'cloud-rain': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0-2.485-2.015-4.5-4.5-4.5a4.5 4.5 0 00-4.37 3.39A3.375 3.375 0 107.125 12h11.25" />
    </svg>
  ),
  'snowflake': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18M3 12h18M5.636 5.636l12.728 12.728M18.364 5.636L5.636 18.364" />
    </svg>
  ),
  'cloud-fog': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2 12h20M4 16h16M6 20h12M4 8h16" />
    </svg>
  ),
  'wind': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      <path d="M9.5 5.5A2.5 2.5 0 0112 3c3 0 5.5 2 5.5 5M6.5 9A2.5 2.5 0 019 6.5c2.5 0 4 1.5 4 3.5" />
    </svg>
  ),
  'cloud-lightning': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  'eye-off': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
    </svg>
  ),
  'thermometer': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  ),
  'thermometer-snowflake': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  ),
  'thermometer-sun': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
    </svg>
  ),
  'alert-triangle': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  ),
  'check-circle': (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  'info': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
    </svg>
  ),
  'car': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" />
    </svg>
  ),
}

// Severity styles
const severityStyles = {
  danger: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    text: 'text-red-500',
    badge: 'bg-red-500',
    icon: 'text-red-500',
  },
  warning: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-500',
    badge: 'bg-amber-500',
    icon: 'text-amber-500',
  },
  info: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-500',
    badge: 'bg-blue-500',
    icon: 'text-blue-500',
  },
}

export default function WeatherAlerts({ userLocation, compact = false, onDismiss }) {
  const { t } = useTranslation()
  const [alertData, setAlertData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [dismissedAlerts, setDismissedAlerts] = useState(() => {
    try {
      const saved = localStorage.getItem('dismissedWeatherAlerts')
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })

  // Fetch weather alerts
  const fetchAlerts = useCallback(async () => {
    if (!userLocation?.lat || !userLocation?.lon) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await externalApi.getWeatherAlerts(
        userLocation.lat,
        userLocation.lon,
        userLocation.name || 'Unknown'
      )
      setAlertData(response.data)
    } catch (err) {
      console.error('Failed to fetch weather alerts:', err)
      setError(t('weatherAlerts.fetchError') || 'Failed to load weather alerts')
    } finally {
      setIsLoading(false)
    }
  }, [userLocation, t])

  useEffect(() => {
    fetchAlerts()
    
    // Refresh alerts every 15 minutes
    const interval = setInterval(fetchAlerts, 15 * 60 * 1000)
    return () => clearInterval(interval)
  }, [fetchAlerts])

  // Clean up old dismissed alerts (older than 24 hours)
  useEffect(() => {
    const now = Date.now()
    const cleaned = {}
    Object.entries(dismissedAlerts).forEach(([key, timestamp]) => {
      if (now - timestamp < 24 * 60 * 60 * 1000) {
        cleaned[key] = timestamp
      }
    })
    if (Object.keys(cleaned).length !== Object.keys(dismissedAlerts).length) {
      setDismissedAlerts(cleaned)
      localStorage.setItem('dismissedWeatherAlerts', JSON.stringify(cleaned))
    }
  }, [dismissedAlerts])

  const handleDismissAlert = (alertId) => {
    const updated = { ...dismissedAlerts, [alertId]: Date.now() }
    setDismissedAlerts(updated)
    localStorage.setItem('dismissedWeatherAlerts', JSON.stringify(updated))
    onDismiss?.(alertId)
  }

  const handleDismissAll = () => {
    if (!alertData?.alerts) return
    const updated = { ...dismissedAlerts }
    alertData.alerts.forEach(alert => {
      updated[alert.id] = Date.now()
    })
    setDismissedAlerts(updated)
    localStorage.setItem('dismissedWeatherAlerts', JSON.stringify(updated))
  }

  // Get translated alert text
  const getAlertText = (alert) => {
    const key = alert.i18n_key
    const translated = t(key)
    if (translated === key) {
      // Fallback if translation not found
      return key.split('.').pop().replace(/([A-Z])/g, ' $1').trim()
    }
    return translated
  }

  // Get translated tip text
  const getTipText = (tip) => {
    const key = tip.i18n_key
    const translated = t(key)
    if (translated === key) {
      return key.split('.').pop().replace(/([A-Z])/g, ' $1').trim()
    }
    return translated
  }

  // Filter out dismissed alerts
  const activeAlerts = alertData?.alerts?.filter(
    alert => !dismissedAlerts[alert.id]
  ) || []

  const hasDangerAlerts = activeAlerts.some(a => a.severity === 'danger')
  const hasWarningAlerts = activeAlerts.some(a => a.severity === 'warning')

  // Loading state
  if (isLoading && !alertData) {
    return (
      <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-[var(--color-bg-tertiary)] animate-pulse" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded animate-pulse mb-2" />
            <div className="h-3 w-48 bg-[var(--color-bg-tertiary)] rounded animate-pulse" />
          </div>
        </div>
      </div>
    )
  }

  // Error state
  if (error && !alertData) {
    return (
      <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
        <div className="flex items-center gap-3 text-[var(--color-text-secondary)]">
          {AlertIcons['alert-triangle']}
          <span className="text-sm">{error}</span>
          <button
            onClick={fetchAlerts}
            className="ml-auto text-xs text-[var(--color-primary)] hover:underline"
          >
            {t('common.retry') || 'Retry'}
          </button>
        </div>
      </div>
    )
  }

  // No alerts - all clear
  if (activeAlerts.length === 0) {
    if (compact) return null
    
    return (
      <div className="bg-green-500/10 rounded-xl border border-green-500/30 p-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-full bg-green-500/20 text-green-500">
            {AlertIcons['check-circle']}
          </div>
          <div>
            <p className="font-medium text-green-500">
              {t('weatherAlerts.allClear') || 'Good Driving Conditions'}
            </p>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('weatherAlerts.noActiveAlerts') || 'No weather alerts for your area'}
            </p>
          </div>
          {alertData?.safety_score && (
            <div className="ml-auto text-center">
              <div className="text-2xl font-bold text-green-500">{alertData.safety_score}</div>
              <div className="text-xs text-[var(--color-text-secondary)]">
                {t('weatherAlerts.safetyScore') || 'Safety'}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Compact view (for dashboard widget)
  if (compact) {
    return (
      <div 
        className={`rounded-xl border p-4 cursor-pointer transition-all ${
          hasDangerAlerts 
            ? 'bg-red-500/10 border-red-500/30' 
            : hasWarningAlerts 
            ? 'bg-amber-500/10 border-amber-500/30' 
            : 'bg-blue-500/10 border-blue-500/30'
        }`}
        onClick={() => setIsExpanded(true)}
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full ${
            hasDangerAlerts ? 'bg-red-500/20 text-red-500' :
            hasWarningAlerts ? 'bg-amber-500/20 text-amber-500' :
            'bg-blue-500/20 text-blue-500'
          }`}>
            {AlertIcons[activeAlerts[0]?.icon] || AlertIcons['alert-triangle']}
          </div>
          <div className="flex-1 min-w-0">
            <p className={`font-medium truncate ${
              hasDangerAlerts ? 'text-red-500' :
              hasWarningAlerts ? 'text-amber-500' :
              'text-blue-500'
            }`}>
              {activeAlerts.length} {t('weatherAlerts.activeAlerts') || 'Weather Alerts'}
            </p>
            <p className="text-sm text-[var(--color-text-secondary)] truncate">
              {getAlertText(activeAlerts[0])}
            </p>
          </div>
          <svg className="w-5 h-5 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    )
  }

  // Full expanded view
  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden">
      {/* Header */}
      <div className={`px-4 py-3 border-b border-[var(--color-border)] ${
        hasDangerAlerts ? 'bg-red-500/10' :
        hasWarningAlerts ? 'bg-amber-500/10' :
        'bg-blue-500/10'
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-full ${
              hasDangerAlerts ? 'bg-red-500/20 text-red-500' :
              hasWarningAlerts ? 'bg-amber-500/20 text-amber-500' :
              'bg-blue-500/20 text-blue-500'
            }`}>
              {AlertIcons['alert-triangle']}
            </div>
            <div>
              <h3 className="font-semibold">
                {t('weatherAlerts.title') || 'Weather Driving Alerts'}
              </h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {alertData?.location || 'Your location'}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {alertData?.safety_score !== undefined && (
              <div className="text-center">
                <div className={`text-xl font-bold ${
                  alertData.safety_score >= 80 ? 'text-green-500' :
                  alertData.safety_score >= 50 ? 'text-amber-500' :
                  'text-red-500'
                }`}>
                  {alertData.safety_score}
                </div>
                <div className="text-xs text-[var(--color-text-muted)]">
                  {t('weatherAlerts.safetyScore') || 'Safety'}
                </div>
              </div>
            )}
            
            <button
              onClick={handleDismissAll}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] px-2 py-1"
            >
              {t('weatherAlerts.dismissAll') || 'Dismiss All'}
            </button>
          </div>
        </div>
      </div>

      {/* Alerts List */}
      <div className="p-4 space-y-3">
        {activeAlerts.map((alert) => {
          const style = severityStyles[alert.severity] || severityStyles.info
          const IconComponent = AlertIcons[alert.icon] || AlertIcons['alert-triangle']
          
          return (
            <div
              key={alert.id}
              className={`${style.bg} ${style.border} border rounded-lg p-3`}
            >
              <div className="flex items-start gap-3">
                <div className={`p-1.5 rounded-lg ${style.bg} ${style.icon}`}>
                  {IconComponent}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-medium ${style.text}`}>
                      {getAlertText(alert)}
                    </span>
                    {alert.value && (
                      <span className="text-sm text-[var(--color-text-secondary)]">
                        {alert.value}{alert.unit}
                      </span>
                    )}
                    <span className={`${style.badge} text-white text-xs px-2 py-0.5 rounded-full`}>
                      {alert.current 
                        ? (t('weatherAlerts.now') || 'Now')
                        : (t('weatherAlerts.upcoming') || 'Upcoming')
                      }
                    </span>
                  </div>
                  
                  {alert.forecast_time && (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {t('weatherAlerts.expectedAt') || 'Expected at'}: {
                        new Date(alert.forecast_time).toLocaleTimeString([], { 
                          hour: '2-digit', 
                          minute: '2-digit' 
                        })
                      }
                    </p>
                  )}
                </div>
                
                <button
                  onClick={() => handleDismissAlert(alert.id)}
                  className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] rounded"
                  title={t('common.dismiss') || 'Dismiss'}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Driving Tips */}
      {alertData?.tips?.length > 0 && (
        <div className="px-4 pb-4">
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              {AlertIcons.car}
              <h4 className="font-medium">
                {t('weatherAlerts.drivingTips') || 'Driving Tips'}
              </h4>
            </div>
            <ul className="space-y-2">
              {alertData.tips.map((tip, index) => (
                <li key={index} className="flex items-start gap-2 text-sm">
                  <span className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    tip.priority === 'high' ? 'bg-red-500' :
                    tip.priority === 'medium' ? 'bg-amber-500' :
                    'bg-blue-500'
                  }`} />
                  <span className="text-[var(--color-text-secondary)]">
                    {getTipText(tip)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Current Conditions Summary */}
      {alertData?.conditions && (
        <div className="px-4 pb-4">
          <div className="flex flex-wrap gap-4 text-xs text-[var(--color-text-muted)]">
            <span>🌡️ {alertData.conditions.temperature}°C</span>
            <span>💧 {alertData.conditions.humidity}%</span>
            <span>💨 {alertData.conditions.wind_speed} km/h</span>
            {alertData.conditions.visibility < 10000 && (
              <span>👁️ {(alertData.conditions.visibility / 1000).toFixed(1)} km</span>
            )}
          </div>
        </div>
      )}

      {/* Last Updated */}
      <div className="px-4 pb-3 flex items-center justify-between text-xs text-[var(--color-text-muted)]">
        <span>
          {t('weatherAlerts.lastUpdated') || 'Updated'}: {
            alertData?.updated 
              ? new Date(alertData.updated).toLocaleTimeString([], { 
                  hour: '2-digit', 
                  minute: '2-digit' 
                })
              : '--'
          }
        </span>
        <button
          onClick={fetchAlerts}
          className="flex items-center gap-1 hover:text-[var(--color-text-primary)]"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {t('common.refresh') || 'Refresh'}
        </button>
      </div>
    </div>
  )
}

// Modal wrapper for compact view expansion
export function WeatherAlertsModal({ isOpen, onClose, userLocation }) {
  const { t } = useTranslation()
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div 
        className="w-full max-w-lg max-h-[80vh] overflow-y-auto bg-[var(--color-bg-primary)] rounded-t-2xl sm:rounded-2xl shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="sticky top-0 bg-[var(--color-bg-primary)] px-4 py-3 border-b border-[var(--color-border)] flex items-center justify-between">
          <h2 className="font-semibold">
            {t('weatherAlerts.title') || 'Weather Driving Alerts'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-[var(--color-bg-tertiary)]"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        {/* Modal Content */}
        <div className="p-4">
          <WeatherAlerts userLocation={userLocation} />
        </div>
      </div>
    </div>
  )
}
