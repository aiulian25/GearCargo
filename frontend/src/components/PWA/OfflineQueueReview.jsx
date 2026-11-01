import OfflineDraftReview from './OfflineDraftReview'
import { getBoundIdentity } from '../../utils/offlineIdentity'
import { useState } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

export default function OfflineQueueReview({ pausedCount, legacyCount, pendingSyncCount, reviewPaused }) {
  const { t } = useTranslation()
  const [showDrafts, setShowDrafts] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmDiscard, setConfirmDiscard] = useState(null)
  if (!pausedCount && !legacyCount && !pendingSyncCount) return null

  const act = async action => {
    setBusy(true)
    setError('')
    try {
      const result = await reviewPaused(action)
      if (action === 'export') {
        const url = URL.createObjectURL(new Blob([JSON.stringify({ version: 1, changes: result.entries }, null, 2)], { type: 'application/json' }))
        const link = document.createElement('a')
        link.href = url
        link.download = 'GearCargo-unsent-changes.json'
        link.click()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
      setConfirmDiscard(null)
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }

  return (
    <section className="my-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 p-3 text-sm space-y-2" aria-label={t('pwa.sync.pausedTitle')}>
      <h4 className="font-medium">{t('pwa.sync.pausedTitle')}</h4>
      {(pausedCount > 0 || pendingSyncCount > 0) && <>
        {pausedCount > 0 && <p>{t('pwa.sync.pausedNotice')} ({pausedCount})</p>}
        <button type="button" disabled={!pausedCount} onClick={() => setShowDrafts(value => !value)}>{t('pwa.sync.recovery.review')}</button>
        {showDrafts && <OfflineDraftReview key={getBoundIdentity()?.generation || 'none'} reviewPaused={reviewPaused} />}
        <div className="flex gap-3">
          <button type="button" disabled={busy} onClick={() => act('export')}>{t('pwa.sync.exportPaused')}</button>
          <button type="button" disabled={busy || !pausedCount} onClick={() => setConfirmDiscard('discard')}>{t('pwa.sync.discardPaused')}</button>
        </div>
      </>}
      {legacyCount > 0 && <>
        <p>{t('pwa.sync.legacyNotice')} ({legacyCount})</p>
        <button type="button" disabled={busy} onClick={() => setConfirmDiscard('discard-legacy')}>{t('pwa.sync.discardLegacy')}</button>
      </>}
      {confirmDiscard && <div role="alert" className="space-y-2">
        <p>{t('pwa.sync.discardConfirm')}</p>
        <div className="flex gap-3">
          <button type="button" disabled={busy} onClick={() => act(confirmDiscard)}>{t('common.confirm')}</button>
          <button type="button" disabled={busy} onClick={() => setConfirmDiscard(null)}>{t('common.cancel')}</button>
        </div>
      </div>}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
