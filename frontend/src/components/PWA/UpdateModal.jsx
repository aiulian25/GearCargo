import { useEffect, useState } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAppUpdate } from '../../contexts/UpdateContext'
import { BUILD } from '../../config/build'

const REPO_URL = 'https://github.com/aiulian25/GearCargo'

const Ic = {
  update: <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12"/><path d="M8 11l4 4 4-4"/><path d="M4 21h16"/></svg>,
  shield: <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>,
  close: <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>,
  github: <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.5v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.6.8.5 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z"/></svg>,
  reload: <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2-9.5L23 10"/></svg>,
}

const TAG_STYLE = {
  new: 'bg-[var(--color-accent)]/15 text-[var(--color-accent)]',
  fix: 'bg-green-500/15 text-green-500',
  security: 'bg-amber-500/15 text-amber-500',
}

export default function UpdateModal() {
  const { t, language } = useTranslation()
  const { open, kind, serverInfo, changelog, newerRelease, closeModal, dismiss, dismissRelease, applyUpdate } = useAppUpdate()
  const [showPkgs, setShowPkgs] = useState(false)
  const [applying, setApplying] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') closeModal() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, closeModal])

  if (!open || (!serverInfo && !newerRelease)) return null

  // A "newer release exists on GitHub" hint (admin-facing) is shown only when
  // there is no in-place container update to apply (that one is actionable).
  const isRelease = !!newerRelease && !kind
  const isSecurity = kind === 'security'
  const lang = (language || 'en').slice(0, 2)
  const notes = changelog?.notes?.[lang] || changelog?.notes?.en || []
  const patched = serverInfo?.patched_packages || []
  const tagLabel = { new: t('update.tagNew') || 'New', fix: t('update.tagFix') || 'Fixed', security: t('update.tagSecurity') || 'Security' }

  const onApply = async () => { setApplying(true); await applyUpdate() }

  return (
    <div className="fixed inset-0 z-[130] flex items-end sm:items-center justify-center sm:p-4">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[1px]" aria-hidden="true" onClick={closeModal} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-title"
        className="relative w-full sm:max-w-md bg-[var(--color-bg-card)] border border-[var(--color-border)]
                   rounded-t-2xl sm:rounded-2xl shadow-xl max-h-[88vh] overflow-y-auto safe-bottom
                   px-5 pb-6 pt-3"
      >
        <div className="w-9 h-1 rounded-full bg-[var(--color-border)] mx-auto mb-3 sm:hidden" aria-hidden="true" />

        <div className="flex items-start gap-3">
          <span className={`w-10 h-10 rounded-xl grid place-items-center shrink-0 ${isSecurity ? 'bg-[var(--color-accent)]/15 text-[var(--color-accent)]' : 'bg-amber-500/15 text-amber-500'}`}>
            {isSecurity ? Ic.shield : Ic.update}
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="update-title" className="text-base font-semibold leading-tight">
              {isRelease
                ? (t('update.newRelease') || 'A newer version is available')
                : isSecurity ? (t('update.securityTitle') || 'Security update installed') : (t('update.available') || 'Update available')}
            </h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5 tabular-nums">
              {isRelease
                ? (t('update.onVersionGithub') || 'You’re on v{current} · v{new} on GitHub').replace('{current}', BUILD.version).replace('{new}', newerRelease.version)
                : isSecurity
                  ? `${t('update.weeklyMaintenance') || 'Weekly maintenance'} · ${serverInfo.build_date?.slice(0, 10) || ''}`
                  : `${(t('update.onVersion') || 'You’re on v{current} · new v{new}').replace('{current}', BUILD.version).replace('{new}', serverInfo.version)}`}
            </p>
          </div>
          <button type="button" onClick={closeModal} aria-label={t('common.close') || 'Close'}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] w-8 h-8 grid place-items-center rounded-lg shrink-0">
            {Ic.close}
          </button>
        </div>

        {/* Newer release available (admin-facing) */}
        {isRelease && (
          <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-3.5">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">
              {t('update.newReleaseLead') || 'A newer version has been published.'}
            </p>
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed">
              {t('update.newReleaseDesc') || 'Pull the new image tag to upgrade your server — your data is unaffected. Ask your administrator if you don’t manage this server.'}
            </p>
          </div>
        )}

        {/* Feature update — changelog */}
        {!isRelease && !isSecurity && notes.length > 0 && (
          <>
            <p className="mt-4 mb-2 text-[11px] font-semibold tracking-wider uppercase text-[var(--color-text-muted)]">
              {t('update.whatsNew') || 'What’s new'}
            </p>
            <ul className="flex flex-col gap-2.5">
              {notes.map((n, i) => (
                <li key={i} className="flex gap-2.5 text-sm">
                  <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${TAG_STYLE[n.type] || TAG_STYLE.new}`}>
                    {tagLabel[n.type] || n.type}
                  </span>
                  <span className="min-w-0">
                    <span className="text-[var(--color-text-primary)]">{n.title}</span>
                    {n.desc && <small className="block text-[var(--color-text-muted)] text-xs mt-0.5 leading-relaxed">{n.desc}</small>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {/* Security rebuild */}
        {!isRelease && isSecurity && (
          <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-3.5">
            <div className="flex items-center gap-2 font-medium text-sm text-[var(--color-text-primary)]">
              <span className="text-[var(--color-accent)] shrink-0">{Ic.shield}</span>
              {t('update.securityLead') || 'Latest operating-system security patches'}
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed">
              {t('update.securityDesc') || 'We refreshed the app with this week’s OS security fixes. The app itself didn’t change — your data is unchanged. Reload to run the patched build.'}
            </p>
            {patched.length > 0 && (
              <>
                <button type="button" onClick={() => setShowPkgs((v) => !v)}
                  className="mt-2.5 text-xs font-medium text-[var(--color-accent)] hover:underline">
                  {showPkgs
                    ? (t('update.patchedHide') || 'Hide updated packages')
                    : (t('update.patchedShow') || 'Show updated packages ({count})').replace('{count}', patched.length)}
                </button>
                {showPkgs && (
                  <ul className="mt-2 max-h-40 overflow-y-auto text-[11px] font-mono text-[var(--color-text-muted)] space-y-0.5 tabular-nums">
                    {patched.map((p, i) => <li key={i} className="break-all">{p}</li>)}
                  </ul>
                )}
              </>
            )}
          </div>
        )}

        {/* GitHub link (feature/security only — release mode has its own button) */}
        {!isRelease && (
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer"
            className="mt-4 flex items-center gap-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-3 py-2.5 text-sm text-[var(--color-text-primary)] hover:border-[var(--color-accent)]">
            <span className="shrink-0">{Ic.github}</span>
            <span className="min-w-0 flex-1">
              {isSecurity ? (t('update.viewHistory') || 'See build & release history') : (t('update.viewChangelog') || 'View full changelog')}
              <small className="block text-[var(--color-text-muted)] text-[11px] truncate">github.com/aiulian25/GearCargo</small>
            </span>
            <span className="text-[var(--color-text-muted)] shrink-0" aria-hidden="true">↗</span>
          </a>
        )}

        {/* Actions */}
        <div className="flex gap-2.5 mt-5">
          <button type="button" onClick={isRelease ? dismissRelease : dismiss}
            className="px-4 py-3 rounded-xl border border-[var(--color-border)] text-[var(--color-text-secondary)] text-sm font-medium hover:text-[var(--color-text-primary)] shrink-0">
            {t('update.later') || 'Later'}
          </button>
          {isRelease ? (
            <a href={newerRelease.url || REPO_URL} target="_blank" rel="noopener noreferrer" onClick={dismissRelease}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[var(--color-accent)] text-white text-sm font-semibold hover:opacity-90">
              {Ic.github}
              {t('update.viewRelease') || 'View release'}
            </a>
          ) : (
            <button type="button" onClick={onApply} disabled={applying}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[var(--color-accent)] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-60">
              {Ic.reload}
              {applying
                ? (t('update.updating') || 'Updating…')
                : isSecurity ? (t('update.reload') || 'Reload') : (t('update.updateNow') || 'Update now')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
