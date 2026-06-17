import { useTranslation } from '../../contexts/LanguageContext'

/**
 * Suspense fallback for lazily-loaded route chunks (route-level code splitting).
 *
 * Renders a centered spinner that matches the existing auth/route spinner. It is
 * accessible (role="status" + a translated aria-label) and intentionally
 * text-free so it stays unobtrusive during the brief chunk fetch.
 *
 * @param {boolean} [fullscreen] - when true, fills the viewport (used for the
 *   top-level fallback, e.g. auth pages). Otherwise fills the content area so the
 *   app shell / navigation stays visible during in-app navigation.
 */
export default function PageLoader({ fullscreen = false }) {
  const { t } = useTranslation()
  const heightClass = fullscreen ? 'min-h-screen' : 'min-h-[60vh]'

  return (
    <div
      className={`flex items-center justify-center ${heightClass} bg-[var(--color-bg-primary)]`}
      role="status"
      aria-live="polite"
      aria-label={t('common.loading') || 'Loading...'}
    >
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
    </div>
  )
}
