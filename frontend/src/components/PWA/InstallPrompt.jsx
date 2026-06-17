import { useState, useEffect } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

// SVG Icons
const Icons = {
  download: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  ),
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  smartphone: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
    </svg>
  ),
  // iOS Safari "Share" glyph (square with up arrow)
  share: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/>
    </svg>
  ),
  // "Add to Home Screen" (plus inside a square)
  addToHome: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
    </svg>
  ),
}

// iOS does not fire `beforeinstallprompt`; installation is a manual
// Share → "Add to Home Screen" flow, so we detect the platform and show
// instructions instead of a (non-functional) install button.
function isIosDevice() {
  if (typeof window === 'undefined') return false
  const ua = window.navigator.userAgent || ''
  const isIOS = /iPad|iPhone|iPod/.test(ua)
  // iPadOS 13+ reports as "MacIntel" but exposes touch points.
  const isIPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  return isIOS || isIPadOS
}

function isInStandalone() {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  )
}

export default function InstallPrompt() {
  const { t } = useTranslation()
  const [deferredPrompt, setDeferredPrompt] = useState(null)
  const [showPrompt, setShowPrompt] = useState(false)
  const [isInstalled, setIsInstalled] = useState(false)
  const [isIOS, setIsIOS] = useState(false)

  useEffect(() => {
    // Check if already installed (display-mode or iOS navigator.standalone)
    if (isInStandalone()) {
      setIsInstalled(true)
      return
    }

    // Check if prompt was dismissed recently (within 7 days)
    const dismissedTime = localStorage.getItem('pwaPromptDismissed')
    if (dismissedTime) {
      const daysSinceDismissed = (Date.now() - parseInt(dismissedTime)) / (1000 * 60 * 60 * 24)
      if (daysSinceDismissed < 7) {
        return
      }
    }

    // iOS: no beforeinstallprompt — show manual Add-to-Home-Screen guidance.
    if (isIosDevice()) {
      setIsIOS(true)
      const timer = setTimeout(() => setShowPrompt(true), 2500)
      return () => clearTimeout(timer)
    }

    // Other platforms: listen for beforeinstallprompt event
    const handler = (e) => {
      e.preventDefault()
      setDeferredPrompt(e)
      // Show prompt after a short delay
      setTimeout(() => setShowPrompt(true), 2000)
    }

    window.addEventListener('beforeinstallprompt', handler)

    // Listen for successful installation
    window.addEventListener('appinstalled', () => {
      setIsInstalled(true)
      setShowPrompt(false)
      setDeferredPrompt(null)
    })

    return () => {
      window.removeEventListener('beforeinstallprompt', handler)
    }
  }, [])

  const handleInstall = async () => {
    if (!deferredPrompt) return

    deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    
    if (outcome === 'accepted') {
      setIsInstalled(true)
    }
    
    setDeferredPrompt(null)
    setShowPrompt(false)
  }

  const handleDismiss = () => {
    localStorage.setItem('pwaPromptDismissed', Date.now().toString())
    setShowPrompt(false)
  }

  if (!showPrompt || isInstalled) return null

  // iOS: manual instructions (Share → Add to Home Screen)
  if (isIOS) {
    return (
      <div className="fixed bottom-20 left-4 right-4 md:left-auto md:right-4 md:max-w-sm z-50 animate-slide-up">
        <div className="bg-gradient-to-r from-blue-600 to-cyan-500 rounded-2xl p-4 shadow-xl border border-white/10">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center text-white">
              {Icons.smartphone}
            </div>

            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-white text-base mb-1">
                {t('pwa.installTitle') || 'Install GearCargo'}
              </h3>
              <p className="text-white/80 text-sm mb-3">
                {t('pwa.iosInstallDescription') || 'Install this app on your device for the best experience.'}
              </p>

              <ol className="space-y-2 mb-3">
                <li className="flex items-center gap-2 text-white text-sm">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-2xs font-semibold">1</span>
                  <span className="min-w-0">{t('pwa.iosInstallShare') || 'Tap the Share button'}</span>
                  <span className="flex-shrink-0 text-white/90">{Icons.share}</span>
                </li>
                <li className="flex items-center gap-2 text-white text-sm">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-2xs font-semibold">2</span>
                  <span className="min-w-0">{t('pwa.iosInstallAddToHome') || 'Select “Add to Home Screen”'}</span>
                  <span className="flex-shrink-0 text-white/90">{Icons.addToHome}</span>
                </li>
              </ol>

              <button
                onClick={handleDismiss}
                className="bg-white text-blue-600 font-semibold px-4 py-2 rounded-lg text-sm hover:bg-blue-50 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-600"
              >
                {t('pwa.gotIt') || 'Got it'}
              </button>
            </div>

            <button
              onClick={handleDismiss}
              className="flex-shrink-0 text-white/60 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-white rounded"
              aria-label={t('common.close') || 'Close'}
            >
              {Icons.close}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Other platforms: native install via beforeinstallprompt
  return (
    <div className="fixed bottom-20 left-4 right-4 md:left-auto md:right-4 md:max-w-sm z-50 animate-slide-up">
      <div className="bg-gradient-to-r from-blue-600 to-cyan-500 rounded-2xl p-4 shadow-xl border border-white/10">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center text-white">
            {Icons.smartphone}
          </div>

          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white text-base mb-1">
              {t('pwa.installTitle') || 'Install GearCargo'}
            </h3>
            <p className="text-white/80 text-sm mb-3">
              {t('pwa.installDescription') || 'Add to home screen for the best experience with offline access.'}
            </p>

            <div className="flex items-center gap-2">
              <button
                onClick={handleInstall}
                className="flex items-center gap-2 bg-white text-blue-600 font-semibold px-4 py-2 rounded-lg text-sm hover:bg-blue-50 transition-colors focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-600"
              >
                {Icons.download}
                {t('pwa.installButton') || 'Install'}
              </button>
              <button
                onClick={handleDismiss}
                className="text-white/80 hover:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-white rounded"
              >
                {t('pwa.notNow') || 'Not now'}
              </button>
            </div>
          </div>

          <button
            onClick={handleDismiss}
            className="flex-shrink-0 text-white/60 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-white rounded"
            aria-label={t('common.close') || 'Close'}
          >
            {Icons.close}
          </button>
        </div>
      </div>
    </div>
  )
}
