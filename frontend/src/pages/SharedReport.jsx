/**
 * GearCargo - Public Shared Report viewer (F05)
 *
 * Read-only, unauthenticated view of an expense report behind a signed,
 * expiring, revocable token. Renders only aggregate data returned by the
 * public API; no app shell / navigation (it is a standalone shareable page).
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { reportsApi } from '../services/api'
import { useTranslation } from '../contexts/LanguageContext'

const CATS = ['fuel', 'service', 'repair', 'tax', 'parking', 'insurance']
const CAT_COLOR = {
  fuel: '#f59e0b', service: '#3b82f6', repair: '#ef4444',
  tax: '#f43f5e', parking: '#a855f7', insurance: '#10b981',
}

export default function SharedReport() {
  const { token } = useParams()
  const { t, language } = useTranslation()
  const [state, setState] = useState({ loading: true, data: null, error: null, status: null })

  useEffect(() => {
    let active = true
    reportsApi.getSharedReport(token)
      .then((res) => { if (active) setState({ loading: false, data: res.data, error: null, status: null }) })
      .catch((err) => {
        if (!active) return
        const status = err.response?.data?.status || (err.response?.status === 404 ? 'invalid' : 'error')
        setState({ loading: false, data: null, error: true, status })
      })
    return () => { active = false }
  }, [token])

  const fmtMoney = (currencyCode, amount) => {
    const n = Number(amount) || 0
    try {
      return new Intl.NumberFormat(language || 'en', { style: 'currency', currency: currencyCode || 'EUR', maximumFractionDigits: 0 }).format(n)
    } catch {
      return `${currencyCode || ''} ${n.toFixed(0)}`
    }
  }
  const fmtDate = (iso) => {
    if (!iso) return ''
    try { return new Date(iso).toLocaleDateString(language || 'en', { year: 'numeric', month: 'short', day: 'numeric' }) }
    catch { return iso }
  }

  // Themed container shared by all states.
  const Shell = ({ children }) => (
    <div className="min-h-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] px-4 py-8">
      <div className="max-w-2xl mx-auto">{children}</div>
    </div>
  )

  if (state.loading) {
    return (
      <Shell>
        <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label={t('common.loading') || 'Loading...'}>
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
        </div>
      </Shell>
    )
  }

  if (state.error) {
    const msg = state.status === 'expired'
      ? (t('sharedReport.expired') || 'This report link has expired.')
      : state.status === 'revoked'
        ? (t('sharedReport.revoked') || 'This report link has been revoked by its owner.')
        : (t('sharedReport.invalid') || 'This report link is invalid or no longer available.')
    return (
      <Shell>
        <div className="flex flex-col items-center justify-center text-center min-h-[60vh] gap-3">
          <div className="w-16 h-16 rounded-2xl bg-[var(--color-bg-secondary)] flex items-center justify-center text-3xl" aria-hidden="true">🔒</div>
          <h1 className="text-lg font-semibold">{t('sharedReport.unavailableTitle') || 'Report unavailable'}</h1>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-xs">{msg}</p>
        </div>
      </Shell>
    )
  }

  const d = state.data
  const cats = CATS.filter((k) => (d.totals?.[k] || 0) > 0 || (d.entry_counts?.[k] || 0) > 0)
  const grand = d.totals?.grand_total || 0

  return (
    <Shell>
      {/* Header */}
      <header className="mb-6">
        <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide">{d.app_name || 'GearCargo'}</p>
        <h1 className="text-xl font-bold mt-1">{d.label || (t('sharedReport.title') || 'Expense Report')}</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          {d.period_label} · {fmtDate(d.start_date)} – {fmtDate(d.end_date)}
        </p>
        <span className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-1 rounded-full text-2xs bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]">
          {t('sharedReport.readOnly') || 'Read-only shared report'}
        </span>
      </header>

      {/* Grand total */}
      <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6 mb-4">
        <p className="text-sm text-[var(--color-text-secondary)] mb-1">{t('sharedReport.total') || 'Total expenses'}</p>
        <p className="text-3xl font-bold">{fmtMoney(d.currency, grand)}</p>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          {(t('sharedReport.entriesVehicles') || '{entries} entries · {vehicles} vehicle(s)')
            .replace('{entries}', String(d.entry_counts?.total || 0))
            .replace('{vehicles}', String(d.vehicle_count || 0))}
        </p>
      </div>

      {/* By category */}
      {cats.length > 0 && (
        <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6 mb-4">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3">{t('charts.byCategory') || 'By Category'}</h2>
          <ul className="space-y-2">
            {cats.map((k) => (
              <li key={k} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: CAT_COLOR[k] }} />
                  <span className="text-sm truncate">{t(`charts.${k}`) || k}</span>
                  <span className="text-2xs text-[var(--color-text-muted)] shrink-0">({d.entry_counts?.[k] || 0})</span>
                </span>
                <span className="text-sm font-medium shrink-0">{fmtMoney(d.currency, d.totals?.[k] || 0)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Vehicles */}
      {d.vehicles?.length > 0 && (
        <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6 mb-4">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3">{t('sharedReport.vehicles') || 'Vehicles'}</h2>
          <ul className="flex flex-wrap gap-2">
            {d.vehicles.map((v, i) => (
              <li key={i} className="px-3 py-1.5 rounded-lg bg-[var(--color-bg-tertiary)] text-sm">{v.name}</li>
            ))}
          </ul>
        </div>
      )}

      {/* PDF download */}
      <a
        href={reportsApi.sharedPdfUrl(token)}
        className="btn-primary w-full flex items-center justify-center gap-2"
        target="_blank" rel="noopener noreferrer"
      >
        {t('sharedReport.downloadPdf') || 'Download PDF'}
      </a>

      <p className="text-2xs text-[var(--color-text-muted)] text-center mt-4">
        {d.expires_at
          ? (t('sharedReport.expiresOn') || 'This link expires on {date}').replace('{date}', fmtDate(d.expires_at))
          : ''}
      </p>
    </Shell>
  )
}
