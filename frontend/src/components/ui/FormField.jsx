/**
 * Reusable form-field primitive (IMPROVEMENTS.md §2 — Form UX consistency).
 *
 * A foundation for consolidating the add/edit forms incrementally: consistent
 * label, optional hint, and an accessible inline error wired up with the input.
 * It does NOT own the input itself — render any control (e.g. a react-hook-form
 * `register(...)` input) as children, so it drops into existing forms without a
 * risky rewrite.
 *
 * Accessibility: associates the label with the control, and exposes the error
 * via aria-describedby + role="alert" so screen readers announce it. Pass the
 * same `id` to your input and provide it here.
 *
 * Example:
 *   <FormField id="amount" label={t('addFuel.totalCost')} error={errors.amount?.message}>
 *     <input id="amount" type="number" inputMode="decimal"
 *            className="input" {...register('amount')} />
 *   </FormField>
 */
export default function FormField({ id, label, hint, error, required = false, children, className = '' }) {
  const errorId = id ? `${id}-error` : undefined
  const hintId = id ? `${id}-hint` : undefined

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="block text-xs text-[var(--color-text-muted)] mb-1">
          {label}{required && <span aria-hidden="true"> *</span>}
        </label>
      )}
      {children}
      {hint && !error && (
        <p id={hintId} className="text-2xs text-[var(--color-text-muted)] mt-1 leading-relaxed">{hint}</p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs text-red-500 mt-1 leading-relaxed">{error}</p>
      )}
    </div>
  )
}
