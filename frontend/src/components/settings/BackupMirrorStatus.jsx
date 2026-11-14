import { useTranslation } from '../../contexts/LanguageContext'
import { useDateFormat } from '../../hooks/useDateFormat'

const WAITING_KEY = 'backup.mirror.waiting'
const MESSAGE_KEYS = {
  waiting: WAITING_KEY,
  unavailable: 'backup.mirror.unavailable',
  failed: 'backup.mirror.failed',
}
const STATE_STYLES = {
  current: 'bg-green-500/10 text-green-600 dark:text-green-400',
  waiting: 'bg-(--color-bg-tertiary) text-(--color-text-secondary)',
  unavailable: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  failed: 'bg-red-500/10 text-red-600 dark:text-red-400',
}

function statusMessage(mirror, t, formatDateTime) {
  if (mirror.state !== 'current') return t(MESSAGE_KEYS[mirror.state] ?? WAITING_KEY)
  if (!mirror.last_copied_at) return t(WAITING_KEY)
  return t('backup.mirror.current', { date: formatDateTime(mirror.last_copied_at) })
}

/** Whether the operator's second copy of the backups is current. Shown only when one is configured. */
export default function BackupMirrorStatus({ mirror }) {
  const { t } = useTranslation()
  const { formatDateTime } = useDateFormat()
  return (
    <p role="status" className={`rounded-lg p-3 mb-4 text-sm ${STATE_STYLES[mirror.state] ?? STATE_STYLES.waiting}`}>
      <span className="font-medium">{t('backup.mirror.title')}:</span> {statusMessage(mirror, t, formatDateTime)}
    </p>
  )
}
