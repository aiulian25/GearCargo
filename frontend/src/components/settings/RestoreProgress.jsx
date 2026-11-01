import { useEffect, useState } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { backupApi } from '../../services/api'

const phases = {
  validating: 'validating', validating_database: 'validating', snapshotting: 'staging',
  staging: 'staging', importing: 'applying', publishing_files: 'applying',
  publishing_directories: 'applying', applying_database: 'applying', committing: 'applying',
  rolling_back: 'recovering', completed: 'finishing', rolled_back: 'finishing',
}

export default function RestoreProgress({ active, failure }) {
  const { t } = useTranslation()
  const [status, setStatus] = useState(null)
  const maintenance = !!status?.maintenance
  useEffect(() => {
    let cancelled = false
    const refresh = async () => {
      try {
        const response = await backupApi.getRecoveryStatus()
        if (!cancelled) setStatus(response.data)
      } catch {
        // Keep the last known state while the server is restarting/recovering.
      }
    }
    refresh()
    const timer = (active || maintenance) ? setInterval(refresh, 1500) : null
    return () => { cancelled = true; if (timer) clearInterval(timer) }
  }, [active, maintenance])

  if (failure) {
    return (
      <div role="alert" className="card p-4 mb-4 text-sm space-y-2">
        <p>{t(failure.state === 'rolled_back' ? 'backup.recovery.rolledBack' : 'backup.recovery.required')}</p>
        {failure.id && <p>{t('backup.recovery.reference', { id: failure.id })}</p>}
      </div>
    )
  }
  if (!active && !maintenance) return null
  if (status?.phase === 'recovery_required') {
    return <div role="alert" className="card p-4 mb-4 text-sm">{t('backup.recovery.required')}</div>
  }
  const phase = phases[status?.phase] || (active ? 'validating' : 'recovering')
  return (
    <div role="status" className="card p-4 mb-4 text-sm space-y-2">
      <p className="font-medium">{t(`backup.recovery.${phase}`)}</p>
      <p>{t('backup.recovery.maintenance')}</p>
    </div>
  )
}
