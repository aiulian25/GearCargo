import { useTranslation } from '../../contexts/LanguageContext'
import { useAppUpdate } from '../../contexts/UpdateContext'

/**
 * "dev" badge shown in the header on local/dev builds in place of the green
 * "Online" indicator. It is an unmistakable marker that you are NOT on a
 * production container, and is always clickable — tapping it opens the update
 * dialog as a preview (loaded from the local version.json) so you can see
 * exactly what production users will get before pushing.
 */
export default function DevPill() {
  const { t } = useTranslation()
  const { openModal } = useAppUpdate()

  return (
    <button
      type="button"
      onClick={openModal}
      aria-label={t('update.devPillAria') || 'Development build — tap to preview the update dialog'}
      title={t('update.devPillAria') || 'Development build — tap to preview the update dialog'}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold
                 bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 border border-indigo-500/30
                 hover:bg-indigo-500/25 transition-colors whitespace-nowrap
                 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
    >
      <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" aria-hidden="true" />
      {t('update.devPill') || 'dev'}
    </button>
  )
}
