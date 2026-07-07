import { useTranslation } from '../../contexts/LanguageContext'
import { useAppUpdate } from '../../contexts/UpdateContext'

/**
 * Amber "Update" pill shown in the header when a newer build is available —
 * replaces the green "Online" status. Tapping it opens the details modal.
 */
export default function UpdatePill() {
  const { t } = useTranslation()
  const { available, newerRelease, openModal } = useAppUpdate()
  if (!available && !newerRelease) return null

  return (
    <button
      type="button"
      onClick={openModal}
      aria-label={t('update.pillAria') || 'App update available — tap for details'}
      className="update-pill-pulse flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold
                 bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30
                 hover:bg-amber-500/25 transition-colors whitespace-nowrap
                 focus:outline-none focus:ring-2 focus:ring-amber-500/50"
    >
      <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" aria-hidden="true" />
      {t('update.pill') || 'Update'}
    </button>
  )
}
