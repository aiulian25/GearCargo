import { useState, useEffect } from 'react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { useTranslation } from '../../contexts/LanguageContext'

// SVG Icons
const Icons = {
  refresh: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
  close: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  info: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  ),
}

export default function UpdatePrompt() {
  const { t } = useTranslation()
  const [showReload, setShowReload] = useState(false)
  const [showOfflineReady, setShowOfflineReady] = useState(false)

  const {
    needRefresh: [needRefresh, setNeedRefresh],
    offlineReady: [offlineReady, setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(r) {
      if (r) {
        // Check for updates every 60 minutes
        setInterval(() => {
          r.update()
        }, 60 * 60 * 1000)
      }
    },
    onRegisterError(error) {
      console.error('SW registration error', error)
    },
    immediate: true,
  })

  // Also check for updates when app regains focus (e.g. user switches back to app)
  useEffect(() => {
    let lastCheck = Date.now()
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastCheck > 5 * 60 * 1000) {
        lastCheck = Date.now()
        navigator.serviceWorker?.getRegistration().then(r => r?.update())
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  useEffect(() => {
    if (needRefresh) {
      setShowReload(true)
    }
  }, [needRefresh])

  useEffect(() => {
    if (offlineReady) {
      setShowOfflineReady(true)
      // Auto-hide offline ready message after 5 seconds
      const timer = setTimeout(() => {
        setShowOfflineReady(false)
        setOfflineReady(false)
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [offlineReady, setOfflineReady])

  const handleUpdate = () => {
    updateServiceWorker(true)
    setShowReload(false)
  }

  const handleDismissUpdate = () => {
    setShowReload(false)
    setNeedRefresh(false)
  }

  const handleDismissOffline = () => {
    setShowOfflineReady(false)
    setOfflineReady(false)
  }

  // Update available prompt
  if (showReload) {
    return (
      <div className="fixed top-4 left-4 right-4 md:left-auto md:right-4 md:max-w-sm z-50 animate-slide-down">
        <div className="bg-amber-500 rounded-xl p-4 shadow-xl">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center text-white">
              {Icons.refresh}
            </div>
            
            <div className="flex-1 min-w-0">
              <h4 className="font-semibold text-white text-sm mb-1">
                {t('pwa.updateAvailable') || 'Update Available'}
              </h4>
              <p className="text-white/90 text-xs mb-2">
                {t('pwa.updateDescription') || 'A new version is ready. Refresh to update.'}
              </p>
              
              <div className="flex items-center gap-2">
                <button
                  onClick={handleUpdate}
                  className="bg-white text-amber-600 font-medium px-3 py-1.5 rounded-lg text-xs hover:bg-amber-50 transition-colors"
                >
                  {t('pwa.refreshNow') || 'Refresh Now'}
                </button>
                <button
                  onClick={handleDismissUpdate}
                  className="text-white/80 hover:text-white px-2 py-1.5 text-xs"
                >
                  {t('pwa.later') || 'Later'}
                </button>
              </div>
            </div>
            
            <button
              onClick={handleDismissUpdate}
              className="flex-shrink-0 text-white/60 hover:text-white transition-colors"
              aria-label={t('common.close') || 'Close'}
            >
              {Icons.close}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Offline ready notification
  if (showOfflineReady) {
    return (
      <div className="fixed top-4 left-4 right-4 md:left-auto md:right-4 md:max-w-sm z-50 animate-slide-down">
        <div className="bg-emerald-500 rounded-xl p-4 shadow-xl">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-10 h-10 bg-white/20 rounded-lg flex items-center justify-center text-white">
              {Icons.info}
            </div>
            
            <div className="flex-1 min-w-0">
              <h4 className="font-semibold text-white text-sm mb-0.5">
                {t('pwa.offlineReady') || 'Offline Ready'}
              </h4>
              <p className="text-white/90 text-xs">
                {t('pwa.offlineDescription') || 'App cached and ready to work offline.'}
              </p>
            </div>
            
            <button
              onClick={handleDismissOffline}
              className="flex-shrink-0 text-white/60 hover:text-white transition-colors"
              aria-label={t('common.close') || 'Close'}
            >
              {Icons.close}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
