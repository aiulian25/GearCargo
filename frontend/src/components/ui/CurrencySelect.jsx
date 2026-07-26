/**
 * CurrencySelect — compact per-entry currency picker (F48)
 *
 * Lets a user record the real currency of an expense (e.g. a GBP driver's
 * motorway fill abroad) instead of silently inheriting the app default. The
 * chosen code is stored on the entry and the FX pipeline converts it before
 * summing everywhere (stats, reports, chat).
 *
 * Presentational only: the parent owns the value via react-hook-form's
 * `register('currency')`, so this integrates with the existing form plumbing
 * (default value, edit prefill, dirty tracking) with no extra state.
 *
 * The option set matches the app's supported display currencies
 * (models/user.py — GBP/EUR/RON/USD); any code still round-trips through the
 * ECB-based converter, so this list is a UX convenience, not a hard limit.
 */
import { useTranslation } from '../../contexts/LanguageContext'

export const CURRENCY_CODES = ['GBP', 'EUR', 'RON', 'USD']

export default function CurrencySelect({ register, name = 'currency', className = '' }) {
  const { t } = useTranslation()
  return (
    <div className={className}>
      <label className="block text-xs text-[var(--color-text-muted)] mb-1">
        {t('settings.currency') || 'Currency'}
      </label>
      <select {...register(name)} className="input">
        {CURRENCY_CODES.map((code) => (
          <option key={code} value={code}>{code}</option>
        ))}
      </select>
    </div>
  )
}
