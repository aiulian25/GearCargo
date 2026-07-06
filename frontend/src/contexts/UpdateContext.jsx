import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { BUILD, IS_PUBLISHED_BUILD } from '../config/build'

/**
 * App-update detection (PWA).
 *
 * Polls /api/app-version (the running image's build manifest) and compares it to
 * the build metadata baked into THIS bundle:
 *   • git_sha changed            → a feature update (show the changelog)
 *   • git_sha same, newer date   → a weekly OS-security rebuild (show patched pkgs)
 *
 * Detection is a light periodic fetch — never on the render path — so it doesn't
 * affect dashboard load or offline use. Applying a feature update activates the
 * waiting service worker (new assets); a security rebuild just reloads to run
 * the patched image.
 */
const UpdateContext = createContext(null)

const POLL_MS = 30 * 60 * 1000        // background re-check every 30 min
const FOCUS_THROTTLE_MS = 15 * 60 * 1000

export function UpdateProvider({ children }) {
  const [available, setAvailable] = useState(false)
  const [kind, setKind] = useState(null)          // 'feature' | 'security'
  const [serverInfo, setServerInfo] = useState(null)
  const [changelog, setChangelog] = useState(null) // parsed /version.json
  const [open, setOpen] = useState(false)
  const dismissedRef = useRef(null)               // "sha:date" the user tapped "Later" on

  const check = useCallback(async () => {
    if (!IS_PUBLISHED_BUILD) return                // local dev — no update UI
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return
    try {
      const res = await fetch('/api/app-version', { credentials: 'include', cache: 'no-store' })
      if (!res.ok) return                          // 401 (logged out) / error → ignore
      const info = await res.json()
      const sha = info.git_sha || ''
      const date = info.build_date || ''

      let nextKind = null
      if (sha && sha !== 'dev' && sha !== BUILD.gitSha) nextKind = 'feature'
      else if (sha && sha === BUILD.gitSha && date && BUILD.buildDate && date > BUILD.buildDate) nextKind = 'security'

      if (!nextKind) { setAvailable(false); setKind(null); return }
      if (dismissedRef.current === `${sha}:${date}`) return

      setServerInfo(info)
      setKind(nextKind)
      setAvailable(true)

      if (nextKind === 'feature') {
        try {
          const vr = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
          if (vr.ok) setChangelog(await vr.json())
        } catch { /* changelog is optional */ }
      }
    } catch { /* network/parse error → ignore, retry next tick */ }
  }, [])

  useEffect(() => {
    check()
    const id = setInterval(check, POLL_MS)
    let last = Date.now()
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - last > FOCUS_THROTTLE_MS) {
        last = Date.now(); check()
      }
    }
    // Going offline hides the pill so the header falls back to the Online/
    // Offline indicator; reconnecting re-checks and re-surfaces it if still due.
    const onOffline = () => setAvailable(false)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('online', check)
    window.addEventListener('offline', onOffline)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('online', check)
      window.removeEventListener('offline', onOffline)
    }
  }, [check])

  const applyUpdate = useCallback(async () => {
    try {
      const reg = await navigator.serviceWorker?.getRegistration?.()
      if (kind === 'feature' && reg?.waiting) {
        let reloaded = false
        const reload = () => { if (!reloaded) { reloaded = true; window.location.reload() } }
        navigator.serviceWorker.addEventListener('controllerchange', reload)
        reg.waiting.postMessage({ type: 'SKIP_WAITING' })
        setTimeout(reload, 1500)   // safety net if controllerchange doesn't fire
        return
      }
    } catch { /* fall through to a plain reload */ }
    window.location.reload()
  }, [kind])

  const dismiss = useCallback(() => {
    if (serverInfo) dismissedRef.current = `${serverInfo.git_sha}:${serverInfo.build_date}`
    setOpen(false)
    setAvailable(false)
  }, [serverInfo])

  const value = {
    available, kind, serverInfo, changelog,
    open, openModal: () => setOpen(true), closeModal: () => setOpen(false),
    applyUpdate, dismiss,
  }
  return <UpdateContext.Provider value={value}>{children}</UpdateContext.Provider>
}

export function useAppUpdate() {
  const ctx = useContext(UpdateContext)
  if (!ctx) throw new Error('useAppUpdate must be used within UpdateProvider')
  return ctx
}

export default UpdateContext
