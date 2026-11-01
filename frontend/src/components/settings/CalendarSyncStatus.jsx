import { useEffect, useState } from 'react'
import { calendarApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

export default function CalendarSyncStatus() {
  const { t } = useTranslation()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(false)
  const [version, setVersion] = useState(0)
  const [retrying, setRetrying] = useState(null)
  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const response = await calendarApi.getSyncJobStatus()
        if (active) { setStatus(response.data); setError(false) }
      } catch { if (active) setError(true) }
    }
    load()
    const timer = setInterval(load, 10000)
    return () => { active = false; clearInterval(timer) }
  }, [version])
  const retry = async id => {
    setRetrying(id)
    try { await calendarApi.retrySync(id); setVersion(value => value + 1) }
    catch { setError(true) }
    finally { setRetrying(null) }
  }
  return <section aria-label={t('calendarQueue.title')} className="space-y-2">
    <h3 className="text-sm font-medium">{t('calendarQueue.title')}</h3>
    <p className="text-xs text-(--color-text-muted)">{t('calendarQueue.explanation')}</p>
    {error && <p role="alert" className="text-sm text-red-500">{t('calendarQueue.unavailable')}</p>}
    {(status?.sources || []).map(source => <div key={source.id} className="rounded-lg border border-(--color-border) p-3 text-sm space-y-1">
      <p className="font-medium">{source.name}</p>
      {!source.enabled && <p>{t('calendarQueue.disabled')}</p>}
      <p>{t('calendarQueue.applied')}: {source.synced} · {t('calendarQueue.waiting')}: {source.pending}</p>
      {(source.retrying > 0 || source.failed > 0) && <p>{t('calendarQueue.retrying')}: {source.retrying} · {t('calendarQueue.failed')}: {source.failed}</p>}
      {source.paused > 0 && <p>{t('calendarQueue.paused')}: {source.paused}</p>}
      {source.next_attempt_at && <p>{t('calendarQueue.nextRetry')}: {new Date(`${source.next_attempt_at}Z`).toLocaleString()}</p>}
      {(source.retrying > 0 || source.failed > 0 || source.paused > 0) && <button type="button" className="btn btn-secondary btn-sm"
        disabled={!source.enabled || retrying === source.id} onClick={() => retry(source.id)}>{t('calendarQueue.retry')}</button>}
    </div>)}
  </section>
}
