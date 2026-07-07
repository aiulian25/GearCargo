import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { BUILD, IS_PUBLISHED_BUILD, IS_DEV_BUILD } from '../config/build'

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

/** Return true when semver string `a` is strictly newer than `b` (major.minor.patch). */
function isNewerVersion(a, b) {
  const pa = String(a).split('.').map((n) => parseInt(n, 10) || 0)
  const pb = String(b).split('.').map((n) => parseInt(n, 10) || 0)
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) > (pb[i] || 0)) return true
    if ((pa[i] || 0) < (pb[i] || 0)) return false
  }
  return false
}

export function UpdateProvider({ children }) {
  const [available, setAvailable] = useState(false)
  const [kind, setKind] = useState(null)          // 'feature' | 'security'
  const [serverInfo, setServerInfo] = useState(null)
  const [changelog, setChangelog] = useState(null) // parsed /version.json
  const [open, setOpen] = useState(false)
  // "A newer version exists on GitHub" — only when the server opts in
  // (UPDATE_CHECK_ENABLED). Independent of the container-vs-browser update above,
  // so version-pinned deployments can still learn a newer release is out.
  const [newerRelease, setNewerRelease] = useState(null)  // { version, url, publishedAt }
  const dismissedRef = useRef(null)               // "sha:date" the user tapped "Later" on
  const releaseDismissedRef = useRef(null)        // release version the user dismissed

  const check = useCallback(async () => {
    if (!IS_PUBLISHED_BUILD) return                // local dev — no update UI
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return
    try {
      const res = await fetch('/api/app-version', { credentials: 'include', cache: 'no-store' })
      if (!res.ok) return                          // 401 (logged out) / error → ignore
      const info = await res.json()
      const sha = info.git_sha || ''
      const date = info.build_date || ''

      // Newer-release hint (evaluated regardless of the feature/security result
      // below, so a pinned deployment still surfaces it).
      const rel = info.latest_release
      if (rel && rel.version && isNewerVersion(rel.version, info.version || BUILD.version)
          && releaseDismissedRef.current !== rel.version) {
        setNewerRelease({ version: rel.version, url: rel.url || '', publishedAt: rel.published_at || '' })
      } else {
        setNewerRelease(null)
      }

      let nextKind = null
      if (sha && sha !== 'dev' && sha !== BUILD.gitSha) nextKind = 'feature'
      else if (sha && sha === BUILD.gitSha && date && BUILD.buildDate && date > BUILD.buildDate) nextKind = 'security'

      if (!nextKind) { setAvailable(false); setKind(null); return }
      if (dismissedRef.current === `${sha}:${date}`) return

      setServerInfo(info)
      setKind(nextKind)
      setAvailable(true)

      // Proactively pull the new service worker the moment we detect a new build
      // (not just at click time), so a waiting worker is ready when the user taps
      // Update — making the apply near-instant and reliable.
      navigator.serviceWorker?.getRegistration?.().then((r) => r && r.update()).catch(() => {})

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

  // Apply an update by ACTIVATING the new service worker, then reloading — never
  // a bare reload of the stale shell.
  //
  // Why the old bare-reload was wrong: the pill fires the instant /api/app-version
  // reports a new git_sha (network), but the new SW is only discovered by a
  // periodic update() check — so at click time there is usually NO waiting worker.
  // A plain window.location.reload() is then intercepted by the still-active OLD
  // SW, which serves the OLD precached index.html + bundle → same git_sha → the
  // prompt reappears forever (the "clear cache to update" pain). Here we force the
  // new SW to download + install, tell it to skip waiting, and only reload once it
  // has taken control (controllerchange) so the fresh assets are actually served.
  const applyUpdate = useCallback(async () => {
    const reg = await navigator.serviceWorker?.getRegistration?.().catch(() => null)
    if (!reg) { window.location.reload(); return }  // dev / no SW support

    let reloaded = false
    const doReload = () => { if (!reloaded) { reloaded = true; window.location.reload() } }

    // Skip-waiting a specific worker, then reload when it takes control.
    const activate = (worker) => {
      navigator.serviceWorker.addEventListener('controllerchange', doReload, { once: true })
      worker.postMessage({ type: 'SKIP_WAITING' })
      setTimeout(doReload, 3000)   // safety net if controllerchange doesn't fire
    }

    // 1) A new worker is already waiting → activate it now.
    if (reg.waiting) { activate(reg.waiting); return }

    // 2) None waiting yet → force an update check and wait for the new worker to
    //    finish installing, THEN activate it.
    const waitForInstall = (worker) => {
      worker.addEventListener('statechange', () => {
        if (worker.state === 'installed') activate(worker)          // now the waiting worker
        else if (worker.state === 'activated') doReload()           // already took over
      })
    }

    try { await reg.update() } catch { /* offline / fetch error */ }

    if (reg.waiting) { activate(reg.waiting); return }
    if (reg.installing) { waitForInstall(reg.installing); return }

    // 3) Genuinely nothing new to install (e.g. the active SW already matches).
    //    A plain reload is safe here and cannot loop, because there is no newer
    //    build to keep detecting.
    doReload()
  }, [])

  const dismiss = useCallback(() => {
    if (serverInfo) dismissedRef.current = `${serverInfo.git_sha}:${serverInfo.build_date}`
    setOpen(false)
    setAvailable(false)
  }, [serverInfo])

  // Dismiss just the "newer release" hint (remembers the version so it won't nag
  // again for the same release).
  const dismissRelease = useCallback(() => {
    setNewerRelease((prev) => { if (prev) releaseDismissedRef.current = prev.version; return null })
    setOpen(false)
  }, [])

  // Open the details modal. On a dev build there is no real update to show, so
  // we load the local /version.json and synthesise a "feature" manifest — this
  // renders exactly what production users will see on the next update, letting
  // us preview it from the always-clickable dev badge before pushing.
  const openModal = useCallback(async () => {
    if (IS_DEV_BUILD && !serverInfo) {
      let cl = null
      try {
        const vr = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
        if (vr.ok) cl = await vr.json()
      } catch { /* changelog is optional in preview */ }
      if (cl) setChangelog(cl)
      setKind('feature')
      setServerInfo({
        version: cl?.version || 'dev',
        git_sha: 'preview',
        build_date: cl?.date || '',
        patched_packages: [],
      })
    }
    setOpen(true)
  }, [serverInfo])

  const value = {
    available, kind, serverInfo, changelog, isDev: IS_DEV_BUILD,
    newerRelease, dismissRelease,
    open, openModal, closeModal: () => setOpen(false),
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
