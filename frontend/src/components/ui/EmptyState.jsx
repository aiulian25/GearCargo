import { Link } from 'react-router-dom'

/**
 * Reusable, accessible empty-state (IMPROVEMENTS.md §2 — Empty states with guidance).
 *
 * Friendly icon + title + description + a primary CTA, replacing bland/blank
 * tables for first-run users. Matches the existing `card text-center py-12`
 * pattern so it stays consistent with the design system. All text is passed in
 * already-localized by the caller — this component hardcodes no copy.
 *
 * Props:
 *   icon        material-icons-outlined name (string) OR a React node.
 *   title       short heading (localized).
 *   description one-line guidance (localized).
 *   actionLabel CTA label (localized). Renders a CTA when provided.
 *   actionTo    if set, the CTA is a <Link> to this route.
 *   onAction    if set (and no actionTo), the CTA is a <button>.
 */
export default function EmptyState({
  icon = 'inbox',
  title,
  description,
  actionLabel,
  actionTo,
  onAction,
}) {
  let action = null
  if (actionLabel && actionTo) {
    action = <Link to={actionTo} className="btn btn-primary">{actionLabel}</Link>
  } else if (actionLabel && onAction) {
    action = <button type="button" onClick={onAction} className="btn btn-primary">{actionLabel}</button>
  }

  return (
    <div className="card text-center py-12 px-6 flex flex-col items-center" role="status" aria-live="polite">
      {typeof icon === 'string' ? (
        <span className="material-icons-outlined icon-xl text-[var(--color-text-muted)] mb-3" aria-hidden="true">
          {icon}
        </span>
      ) : (
        <span className="text-[var(--color-text-muted)] mb-3" aria-hidden="true">{icon}</span>
      )}
      {title && <h3 className="text-sm font-medium mb-1">{title}</h3>}
      {description && (
        <p className="text-xs text-[var(--color-text-secondary)] mb-4 max-w-xs leading-relaxed">
          {description}
        </p>
      )}
      {action}
    </div>
  )
}
