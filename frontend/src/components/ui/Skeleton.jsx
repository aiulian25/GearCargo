import { useTranslation } from '../../contexts/LanguageContext'

/**
 * Skeleton loading primitives (IMPROVEMENTS.md §2 — Loading & skeleton states).
 *
 * Built on the global `.skeleton` class (animate-pulse, theme-aware) so the look
 * stays consistent with the bespoke skeletons already used across the app, while
 * adding the accessibility those inline placeholders lack: a `role="status"`
 * container that announces a localized "Loading…" to assistive tech once, with
 * the decorative placeholder boxes marked `aria-hidden`.
 */

// A single shimmer box. Pass sizing via className (e.g. "h-4 w-1/2 rounded").
export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />
}

/**
 * Accessible wrapper for a group of skeleton placeholders. Announces loading
 * state to screen readers exactly once via a visually-hidden label.
 */
export function SkeletonScreen({ children, className = '' }) {
  const { t } = useTranslation()
  return (
    <div className={className} role="status" aria-busy="true" aria-live="polite">
      {children}
      <span className="sr-only">{t('common.loading') || 'Loading...'}</span>
    </div>
  )
}

/**
 * A list of placeholder "card" rows — the common shape for list data views.
 * `rows` controls how many are shown.
 */
export function SkeletonList({ rows = 5, className = '' }) {
  return (
    <SkeletonScreen className={`space-y-3 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card p-4 flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-full shrink-0" />
          <div className="flex-1 space-y-2 min-w-0">
            <Skeleton className="h-3.5 w-2/3 rounded" />
            <Skeleton className="h-3 w-1/3 rounded" />
          </div>
          <Skeleton className="h-4 w-12 rounded shrink-0" />
        </div>
      ))}
    </SkeletonScreen>
  )
}

export default Skeleton
