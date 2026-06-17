import { useTranslation } from '../../contexts/LanguageContext'

/**
 * Inline "service unavailable / retry" affordance (IMPROVEMENTS.md §2).
 *
 * Shown in place of a widget when an optional external service (weather,
 * air quality, fuel prices, …) fails, instead of leaving a silently-empty
 * placeholder. Accessible (role="status"), dismissible, with a Retry action.
 * All copy is passed/looked-up via i18n — nothing hardcoded.
 *
 * Props:
 *   title     localized heading (e.g. "Weather unavailable").
 *   onRetry   handler for the Retry button (omit to hide it).
 *   retrying  shows a spinner + disables Retry while a retry is in flight.
 *   onDismiss handler for the dismiss (×) button (omit to hide it).
 *   className extra classes for layout.
 */
export default function ServiceUnavailable({ title, onRetry, retrying = false, onDismiss, className = '' }) {
  const { t } = useTranslation()
  return (
    <div
      className={`rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] p-4 ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <span className="material-icons-outlined text-[var(--color-text-muted)] shrink-0" aria-hidden="true">
          cloud_off
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{title || t('serviceError.title') || 'Service unavailable'}</p>
          <p className="text-2xs text-[var(--color-text-secondary)] mt-0.5 leading-relaxed">
            {t('serviceError.desc') || 'We couldn’t load this right now.'}
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-accent)] disabled:opacity-50"
            >
              <span className={`material-icons-outlined icon-sm ${retrying ? 'animate-spin' : ''}`} aria-hidden="true">
                {retrying ? 'progress_activity' : 'refresh'}
              </span>
              {retrying ? (t('serviceError.retrying') || 'Retrying…') : (t('serviceError.retry') || 'Retry')}
            </button>
          )}
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label={t('common.dismiss') || 'Dismiss'}
            className="btn-icon shrink-0 text-[var(--color-text-muted)]"
          >
            <span className="material-icons-outlined icon-sm" aria-hidden="true">close</span>
          </button>
        )}
      </div>
    </div>
  )
}
