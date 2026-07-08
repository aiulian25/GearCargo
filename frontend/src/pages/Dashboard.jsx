import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { vehicleApi, externalApi, insuranceApi, configApi, dueApi } from '../services/api'
import { useCurrency, useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'
import { isOfflineWriteError, announceOfflineSaved } from '../utils/offlineWrite'
import { formatDate, formatDateShort } from '../utils/dateFormat'
import ServiceUnavailable from '../components/ui/ServiceUnavailable'
import { useConfirm } from '../components/ui/ConfirmDialog'
import ChatModal from '../components/chat/ChatModal'

// Fuel Prices Widget
function FuelPricesWidget({ fuelPrices, currency, t, onRefresh, isRefreshing, lastAutoUpdate, error, onRetry, retrying, onDismiss }) {
  // Use currency from fuel prices API (based on detected country) or fallback to user's currency
  const fuelCurrency = fuelPrices?.currency || currency.symbol

  // Live "Updated X min ago" label — ticks every 30 s
  const [timeAgoLabel, setTimeAgoLabel] = useState(null)
  useEffect(() => {
    const update = () => {
      if (!lastAutoUpdate) { setTimeAgoLabel(null); return }
      const mins = Math.floor((Date.now() - lastAutoUpdate) / 60000)
      if (mins < 1) {
        setTimeAgoLabel(t('fuelPrices.updatedJustNow') || 'Updated just now')
      } else {
        setTimeAgoLabel(
          (t('fuelPrices.updatedAgo') || 'Updated {n} min ago').replace('{n}', mins)
        )
      }
    }
    update()
    const id = setInterval(update, 30000)
    return () => clearInterval(id)
  }, [lastAutoUpdate, t])
  
  // Format last update date
  const formatLastUpdate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      return formatDateShort(date)
    } catch {
      return dateStr
    }
  }

  // Inline error affordance instead of a silently-empty widget on service failure.
  if (error && !fuelPrices) {
    return (
      <ServiceUnavailable
        title={t('serviceError.fuelTitle') || 'Fuel prices unavailable'}
        onRetry={onRetry}
        retrying={retrying}
        onDismiss={onDismiss}
        className="h-full"
      />
    )
  }

  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg">⛽</span>
          <h3 className="text-sm font-semibold">{t('fuelPrices.title')}</h3>
          {fuelPrices?.country && (
            <span className="text-xs px-1.5 py-0.5 bg-[var(--color-bg-tertiary)] rounded text-[var(--color-text-muted)]">
              {fuelPrices.country}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing ? (
            <span className="text-xs text-[var(--color-text-muted)] animate-pulse">
              {t('fuelPrices.autoRefreshing') || 'Refreshing...'}
            </span>
          ) : timeAgoLabel ? (
            <span className="text-xs text-[var(--color-text-muted)]">{timeAgoLabel}</span>
          ) : null}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            title={t('fuelPrices.refresh') || 'Refresh fuel prices'}
            className="p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] transition-colors disabled:opacity-50"
          >
            <svg className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
          </button>
        </div>
      </div>
      
      {/* Prices — a single horizontal row on desktop, stacked on mobile.
          Detected location sits on the left; the three fuel types spread
          across the remaining width with hairline dividers between them. */}
      <div className="px-4 py-4 flex flex-col gap-4 lg:flex-row lg:items-center">
        <p className="text-sm text-[var(--color-text-secondary)] lg:w-52 lg:shrink-0 truncate">
          {fuelPrices?.location || t('common.loading') || 'Loading...'}
        </p>

        <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[var(--color-border)]">
          {[
            { type: 'diesel', labelKey: 'fuelPrices.diesel', color: 'bg-blue-500' },
            { type: 'lpg', labelKey: 'fuelPrices.lpg', color: 'bg-green-500' },
            { type: 'petrol', labelKey: 'fuelPrices.petrol', color: 'bg-yellow-500' },
          ].map((fuel) => {
            const price = fuelPrices?.prices?.[fuel.type]
            return (
              <div key={fuel.type} className="flex items-center justify-between gap-2 py-2 sm:py-0 sm:px-4 sm:first:pl-0 sm:last:pr-0">
                <span className="flex items-center gap-2 min-w-0">
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${fuel.color}`} aria-hidden="true"></span>
                  <span className="text-sm text-[var(--color-text-primary)] truncate">{t(fuel.labelKey)}</span>
                </span>
                <span className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="font-semibold text-[var(--color-text-primary)] tabular-nums">
                    {fuelCurrency}{price != null ? price.toFixed(2) : '--'}/L
                  </span>
                  {price != null && (
                    <svg className="w-3.5 h-3.5 text-[var(--color-text-muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="px-4 py-2.5 border-t border-[var(--color-border)]">
        <p className="text-xs text-[var(--color-text-muted)]">
          {fuelPrices?.source || t('fuelPrices.dataSource')}
          {fuelPrices?.last_update && (
            <span className="ml-1">• {formatLastUpdate(fuelPrices.last_update)}</span>
          )}
        </p>
      </div>
    </div>
  )
}

// Category icon + color per transaction type — mirrors the vehicle Timeline styling.
const TX_CATEGORY = {
  fuel:       { color: 'text-amber-500',  bg: 'bg-amber-500/10',  icon: <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17M15 22H3M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3M6 6h6v5H6z" /> },
  service:    { color: 'text-blue-500',   bg: 'bg-blue-500/10',   icon: <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /> },
  repair:     { color: 'text-red-500',    bg: 'bg-red-500/10',    icon: <path d="M3 21h4L17.5 10.5a2.12 2.12 0 0 0-3-3L4 18v3zM14.5 5.5l4 4" /> },
  tax:        { color: 'text-rose-500',   bg: 'bg-rose-500/10',   icon: <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1zM16 8H8M16 12H8M10 16H8" /> },
  parking:    { color: 'text-purple-500', bg: 'bg-purple-500/10', icon: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 17V7h4a3 3 0 0 1 0 6H9" /></> },
  consumable: { color: 'text-cyan-500',   bg: 'bg-cyan-500/10',   icon: <><path d="M21 8V21H3V8M1 3h22v5H1zM10 12h4" /></> },
  insurance:  { color: 'text-teal-500',   bg: 'bg-teal-500/10',   icon: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /> },
}
const _DEFAULT_TX = { color: 'text-gray-500', bg: 'bg-gray-500/10', icon: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></> }
// Timeline supports these as filter chips; anything else deep-links to the "all" view.
const TIMELINE_FILTER_TYPES = new Set(['fuel', 'service', 'repair', 'tax', 'parking', 'consumable', 'insurance'])

// F12: normalize a policy's payment_frequency to an i18n key under insurance.frequency.*
const INS_FREQ_KEY = {
  monthly: 'monthly', quarterly: 'quarterly',
  'semi-annual': 'semi_annual', semi_annual: 'semi_annual',
  annual: 'annual', yearly: 'annual', one_time: 'annual',
}

// Recent Transactions — fleet-wide feed of the latest cost-bearing entries.
function RecentTransactions({ transactions, loading, error, t, formatCurrency }) {
  const txLink = (tx) => {
    const type = TIMELINE_FILTER_TYPES.has(tx.type) ? tx.type : 'all'
    return `/vehicles/${tx.vehicle_id}/timeline?type=${type}&focus=${tx.id}`
  }

  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
        <span className="text-lg" aria-hidden="true">🧾</span>
        <h3 className="text-sm font-semibold">{t('recentTransactions.title') || 'Recent Transactions'}</h3>
      </div>

      {loading ? (
        <div className="p-4 space-y-3">
          {[0, 1, 2, 3, 4].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}
        </div>
      ) : error || !transactions?.length ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-10">
          <span className="text-3xl mb-2" aria-hidden="true">🚗</span>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {error
              ? (t('recentTransactions.error') || 'Could not load transactions')
              : (t('recentTransactions.empty') || 'No transactions yet')}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-[var(--color-border)]" role="list">
          {transactions.map((tx) => {
            const cat = TX_CATEGORY[tx.type] || _DEFAULT_TX
            const categoryLabel = t(`timeline.${tx.type}`) || tx.type
            return (
              <li key={`${tx.type}-${tx.id}`}>
                <Link
                  to={txLink(tx)}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-inset"
                  aria-label={`${categoryLabel} · ${tx.vehicle_name} · ${tx.description || ''}`}
                >
                  <span className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${cat.bg} ${cat.color}`} aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      {cat.icon}
                    </svg>
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                      {tx.description || categoryLabel}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)] truncate">
                      <span className={cat.color}>{categoryLabel}</span>
                      <span aria-hidden="true"> · </span>
                      {tx.vehicle_name}
                      {/* F12: label the premium's payment frequency (the cost shown
                          is the per-payment premium, not the annualized figure). */}
                      {tx.type === 'insurance' && tx.payment_frequency && (
                        <>
                          <span aria-hidden="true"> · </span>
                          {t(`insurance.frequency.${INS_FREQ_KEY[tx.payment_frequency] || 'annual'}`)}
                        </>
                      )}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-semibold text-[var(--color-text-primary)] tabular-nums whitespace-nowrap">
                      {tx.cost != null ? formatCurrency(tx.cost) : '—'}
                    </p>
                    {tx.date && (
                      <p className="text-xs text-[var(--color-text-muted)] tabular-nums whitespace-nowrap">
                        {formatDateShort(tx.date)}
                      </p>
                    )}
                  </div>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// F4 — icon + accent per due-item kind (reuses the Timeline palette so a fuel-up
// and its due reminder read consistently across the dashboard).
const DUE_KIND = {
  reminder:   { color: 'text-indigo-500', bg: 'bg-indigo-500/10', icon: <><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2 2M12 2h0M5 3 2 6M22 6l-3-3" /></> },
  service:    { color: 'text-blue-500',   bg: 'bg-blue-500/10',   icon: <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /> },
  tax:        { color: 'text-rose-500',   bg: 'bg-rose-500/10',   icon: <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1zM16 8H8M16 12H8M10 16H8" /> },
  insurance:  { color: 'text-teal-500',   bg: 'bg-teal-500/10',   icon: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /> },
  document:   { color: 'text-slate-500',  bg: 'bg-slate-500/10',  icon: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></> },
  parking:    { color: 'text-purple-500', bg: 'bg-purple-500/10', icon: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 17V7h4a3 3 0 0 1 0 6H9" /></> },
  consumable: { color: 'text-cyan-500',   bg: 'bg-cyan-500/10',   icon: <><path d="M21 8V21H3V8M1 3h22v5H1zM10 12h4" /></> },
  fine:       { color: 'text-orange-500', bg: 'bg-orange-500/10', icon: <><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></> },
}
const _DEFAULT_DUE = { color: 'text-gray-500', bg: 'bg-gray-500/10', icon: <><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h0" /></> }

// Severity → left stripe + chip styling. Semantic status colors (not the app accent).
const DUE_SEVERITY = {
  critical: { stripe: 'bg-red-500',   chip: 'text-red-600 dark:text-red-400 bg-red-500/10' },
  warning:  { stripe: 'bg-amber-500', chip: 'text-amber-600 dark:text-amber-400 bg-amber-500/10' },
  info:     { stripe: 'bg-[var(--color-border)]', chip: 'text-[var(--color-text-muted)] bg-[var(--color-bg-tertiary)]' },
}

// Coming up — unified "what needs attention?" feed across all sources (F4).
// F39: only the 2 most urgent rows render by default; the rest sit behind an
// explicit, keyboard/touch-friendly "Show N more" toggle so the card stays
// compact on small PWA viewports. Expansion is pure client state (no refetch).
const DUE_COLLAPSED_COUNT = 2

function DueSoon({ items, loading, error, t, onDismiss }) {
  const [expanded, setExpanded] = useState(false)

  const dueLabel = (it) => {
    if (it.days_left == null) {
      return it.severity === 'critical'
        ? (t('due.replaceNow') || 'Replace now')
        : (t('due.monitor') || 'Monitor')
    }
    if (it.days_left < 0) return t('due.overdue') || 'Overdue'
    if (it.days_left === 0) return t('due.today') || 'Today'
    return (t('due.inDays') || 'In {n} days').replace('{n}', it.days_left)
  }

  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
        <span className="text-lg" aria-hidden="true">📅</span>
        <h3 className="text-sm font-semibold">{t('due.title') || 'Coming up'}</h3>
        {!loading && !error && items?.length > 0 && (
          <span className="ml-auto text-2xs font-semibold tabular-nums px-2 py-0.5 rounded-full bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
            {items.length}
          </span>
        )}
      </div>

      {loading ? (
        <div className="p-4 space-y-3">
          {[0, 1, 2].map(i => <div key={i} className="skeleton h-12 rounded-lg" />)}
        </div>
      ) : error || !items?.length ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-10">
          <span className="text-3xl mb-2" aria-hidden="true">{error ? '⚠️' : '✅'}</span>
          <p className="text-sm text-[var(--color-text-secondary)]">
            {error
              ? (t('due.error') || 'Could not load what’s due')
              : (t('due.empty') || 'Nothing due — you’re all caught up')}
          </p>
        </div>
      ) : (
        <>
          <ul id="due-soon-list" className="divide-y divide-[var(--color-border)]" role="list">
            {(expanded ? items : items.slice(0, DUE_COLLAPSED_COUNT)).map((it) => {
              const cat = DUE_KIND[it.kind] || _DEFAULT_DUE
              const sev = DUE_SEVERITY[it.severity] || DUE_SEVERITY.info
              const kindLabel = t(`due.kind.${it.kind}`) || it.kind
              const similar = it.count > 1
                ? (t('due.similarCount') || '{n} similar items').replace('{n}', it.count)
                : null
              return (
                <li key={`${it.kind}-${it.ref_id}`} className="relative">
                  <span className={`absolute inset-y-0 left-0 w-1 ${sev.stripe}`} aria-hidden="true" />
                  <div className="flex items-center pr-2 hover:bg-[var(--color-bg-tertiary)] transition-colors">
                    <Link
                      to={it.link}
                      className="flex items-center gap-3 pl-5 pr-2 py-3 min-w-0 flex-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-inset"
                      aria-label={`${kindLabel} · ${it.title} · ${dueLabel(it)}${similar ? ` · ${similar}` : ''}`}
                    >
                      <span className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center ${cat.bg} ${cat.color}`} aria-hidden="true">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          {cat.icon}
                        </svg>
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                          {it.title}
                          {it.count > 1 && (
                            <span
                              className="ml-1.5 align-middle text-2xs font-semibold tabular-nums px-1.5 py-0.5 rounded-full bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]"
                              title={similar}
                              aria-hidden="true"
                            >
                              ×{it.count}
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-[var(--color-text-muted)] truncate">
                          <span className={cat.color}>{kindLabel}</span>
                          {it.vehicle_name && (
                            <>
                              <span aria-hidden="true"> · </span>
                              {it.vehicle_name}
                            </>
                          )}
                        </p>
                      </div>
                      <span className={`shrink-0 text-2xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${sev.chip}`}>
                        {dueLabel(it)}
                      </span>
                    </Link>
                    <button
                      type="button"
                      onClick={() => onDismiss?.(it)}
                      title={t('due.dismiss') || 'Dismiss'}
                      aria-label={(t('due.dismissItem') || 'Dismiss {title}').replace('{title}', it.title)}
                      className="shrink-0 p-2.5 rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
          {items.length > DUE_COLLAPSED_COUNT && (
            <button
              type="button"
              onClick={() => setExpanded(v => !v)}
              aria-expanded={expanded}
              aria-controls="due-soon-list"
              className="w-full flex items-center justify-center gap-1.5 px-4 py-3 text-xs font-semibold text-[var(--color-accent)] border-t border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-inset"
            >
              {expanded
                ? (t('due.showLess') || 'Show less')
                : (t('due.showMore') || 'Show {n} more').replace('{n}', items.length - DUE_COLLAPSED_COUNT)}
              <svg
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
                aria-hidden="true"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          )}
        </>
      )}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { currency, setCurrencyFromCountry, formatCurrency } = useCurrency()
  const { t } = useTranslation()
  const { user } = useAuth()
  const confirm = useConfirm()
  const [vehicles, setVehicles] = useState([])
  const [recentTx, setRecentTx] = useState([])
  const [recentTxLoading, setRecentTxLoading] = useState(true)
  const [recentTxError, setRecentTxError] = useState(false)
  // F4 — unified "Due & Expiring" feed.
  const [dueItems, setDueItems] = useState([])
  const [dueLoading, setDueLoading] = useState(true)
  const [dueError, setDueError] = useState(false)
  const [fuelPrices, setFuelPrices] = useState(null)
  const [isRefreshingFuel, setIsRefreshingFuel] = useState(false)
  const [resolvedLocation, setResolvedLocation] = useState(null)
  const [fuelPriceFetchedAt, setFuelPriceFetchedAt] = useState(null)
  const fuelPriceFetchedAtRef = useRef(null)
  const isRefreshingFuelRef = useRef(false)
  // Per-service error/retry/dismiss state for the fuel-price widget.
  const [fuelError, setFuelError] = useState(false)
  const [fuelDismissed, setFuelDismissed] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  // The AI assistant entry only appears when the server has an Ollama
  // integration (enabled + URL). Re-read on mount so it auto-appears once one
  // is added later.
  const [aiEnabled, setAiEnabled] = useState(false)
  const [retryingFuel, setRetryingFuel] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  // Distinguish "vehicles failed to load" (5xx / network) from "genuinely no
  // vehicles" so a transient backend hiccup never shows the onboarding screen
  // (STARTUP_SLOWNESS_INVESTIGATION.md §4.5).
  const [vehiclesError, setVehiclesError] = useState(false)
  const [retryingVehicles, setRetryingVehicles] = useState(false)
  const vehiclesRetryRef = useRef({ attempts: 0, timer: null })
  const [userLocation, setUserLocation] = useState(null)

  // Drag and drop state
  const [draggedVehicle, setDraggedVehicle] = useState(null)
  const [dragOverVehicle, setDragOverVehicle] = useState(null)
  const [isReorderMode, setIsReorderMode] = useState(false)
  const [isSavingOrder, setIsSavingOrder] = useState(false)
  
  // Insurance state
  const [vehicleInsurance, setVehicleInsurance] = useState({}) // { vehicleId: { active: bool, expiring: policy|null } }
  
  // Get user location - checks user's saved location first, then auto-detect
  useEffect(() => {
    // If user has a manually set location and auto-detect is disabled, use it
    if (user && !user.location_auto_detect && user.location_lat && user.location_lon) {
      setUserLocation({
        lat: user.location_lat,
        lon: user.location_lon,
        name: user.location_name,
        saved: true
      })
      return
    }
    
    // Try to use cached location from localStorage for faster load
    const cachedLocation = localStorage.getItem('gearcargo_user_location')
    if (cachedLocation) {
      try {
        const cached = JSON.parse(cachedLocation)
        // Use cached if less than 10 minutes old
        if (cached.timestamp && Date.now() - cached.timestamp < 600000) {
          setUserLocation({ lat: cached.lat, lon: cached.lon, cached: true })
        }
      } catch (e) {
        localStorage.removeItem('gearcargo_user_location')
      }
    }
    
    // Auto-detect location — only available over HTTPS or localhost
    if ('geolocation' in navigator && window.isSecureContext) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const loc = {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            accuracy: position.coords.accuracy // meters
          }
          setUserLocation(loc)
          // Cache the location
          localStorage.setItem('gearcargo_user_location', JSON.stringify({
            lat: loc.lat,
            lon: loc.lon,
            timestamp: Date.now()
          }))
        },
        (error) => {
          console.warn('Geolocation error:', error)
          // Default to London center when geolocation unavailable
          setUserLocation({ lat: 51.5074, lon: -0.1278, default: true })
        },
        { 
          enableHighAccuracy: true,  // Use GPS for better accuracy
          timeout: 10000,             // Increase timeout for GPS
          maximumAge: 300000          // 5 minutes cache
        }
      )
    } else {
      // Default to London center when geolocation not supported
      setUserLocation({ lat: 51.5074, lon: -0.1278, default: true })
    }
  }, [user])
  
  // Fetch vehicles. Returns true on success so the caller can schedule a
  // backoff retry on failure. A failed load sets vehiclesError (NOT an empty
  // list), so the render shows a "starting up / try again" state rather than
  // the onboarding "add your first vehicle" screen.
  const loadVehicles = useCallback(async () => {
    try {
      const vehiclesRes = await vehicleApi.getAll()
      setVehicles(vehiclesRes.data.vehicles || [])
      setVehiclesError(false)
      vehiclesRetryRef.current.attempts = 0
      return true
    } catch (error) {
      console.error('Failed to fetch vehicles:', error)
      setVehiclesError(true)
      return false
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Initial load + automatic exponential backoff while it keeps failing
  // (2s, 4s, 8s, 16s, 30s, 30s…) so a backend that's still starting up
  // recovers on its own without the user touching anything.
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const ok = await loadVehicles()
      if (ok || cancelled) return
      const attempt = (vehiclesRetryRef.current.attempts || 0) + 1
      vehiclesRetryRef.current.attempts = attempt
      if (attempt > 6) return // stop auto-retry; the manual "Try again" remains
      const delay = Math.min(30000, 2000 * 2 ** (attempt - 1))
      vehiclesRetryRef.current.timer = setTimeout(run, delay)
    }
    run()
    return () => {
      cancelled = true
      if (vehiclesRetryRef.current.timer) clearTimeout(vehiclesRetryRef.current.timer)
    }
  }, [loadVehicles])

  const handleRetryVehicles = useCallback(async () => {
    if (vehiclesRetryRef.current.timer) clearTimeout(vehiclesRetryRef.current.timer)
    vehiclesRetryRef.current.attempts = 0
    setRetryingVehicles(true)
    await loadVehicles()
    setRetryingVehicles(false)
  }, [loadVehicles])
  
  // Fetch insurance status for vehicles
  useEffect(() => {
    const fetchInsurance = async () => {
      try {
        const [activeRes, expiringRes] = await Promise.all([
          insuranceApi.getActive(),
          insuranceApi.getExpiring(30)
        ])
        
        const activePolicies = activeRes.data.policies || []
        const expiringPolicies = expiringRes.data.policies || []
        
        // Build a map: vehicleId -> { active, expiring }
        const insuranceMap = {}
        
        // Mark vehicles with active insurance
        activePolicies.forEach(policy => {
          if (policy.vehicle_id) {
            if (!insuranceMap[policy.vehicle_id]) {
              insuranceMap[policy.vehicle_id] = { active: false, expiring: null }
            }
            insuranceMap[policy.vehicle_id].active = true
          }
        })
        
        // Mark vehicles with expiring insurance
        expiringPolicies.forEach(policy => {
          if (policy.vehicle_id) {
            if (!insuranceMap[policy.vehicle_id]) {
              insuranceMap[policy.vehicle_id] = { active: false, expiring: null }
            }
            // Keep the soonest expiring policy
            if (!insuranceMap[policy.vehicle_id].expiring || 
                new Date(policy.end_date) < new Date(insuranceMap[policy.vehicle_id].expiring.end_date)) {
              insuranceMap[policy.vehicle_id].expiring = policy
            }
          }
        })
        
        setVehicleInsurance(insuranceMap)
      } catch (error) {
        console.error('Failed to fetch insurance status:', error)
      }
    }
    fetchInsurance()
  }, [])

  // Fetch the fleet-wide recent transactions feed (5 most recent, all vehicles).
  useEffect(() => {
    let cancelled = false
    const fetchRecent = async () => {
      try {
        const res = await vehicleApi.getRecentTransactions(5)
        if (cancelled) return
        setRecentTx(res.data.transactions || [])
        setRecentTxError(false)
      } catch (error) {
        if (cancelled) return
        console.error('Failed to fetch recent transactions:', error)
        setRecentTxError(true)
      } finally {
        if (!cancelled) setRecentTxLoading(false)
      }
    }
    fetchRecent()
    return () => { cancelled = true }
  }, [])

  // Fetch the unified "Due & Expiring" feed (F4) — one ranked list fleet-wide.
  useEffect(() => {
    let cancelled = false
    const fetchDue = async () => {
      try {
        const res = await dueApi.get(30)
        if (cancelled) return
        setDueItems(res.data.items || [])
        setDueError(false)
      } catch (error) {
        if (cancelled) return
        console.error('Failed to fetch due items:', error)
        setDueError(true)
      } finally {
        if (!cancelled) setDueLoading(false)
      }
    }
    fetchDue()
    return () => { cancelled = true }
  }, [])

  // F40 — dismiss a "Coming up" item: optimistic removal, offline-tolerant
  // (the queued POST replays via Background Sync), with an Undo toast.
  const handleDismissDue = useCallback(async (item) => {
    setDueItems(prev => prev.filter(i => !(i.kind === item.kind && i.ref_id === item.ref_id)))
    try {
      await dueApi.dismiss(item.kind, item.ref_id)
      toast((tst) => (
        <span className="flex items-center gap-3 text-sm">
          {t('due.dismissed') || 'Dismissed'}
          <button
            type="button"
            className="font-semibold text-[var(--color-accent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] rounded"
            onClick={async () => {
              toast.dismiss(tst.id)
              try {
                await dueApi.undismiss(item.kind, item.ref_id)
                const res = await dueApi.get(30)
                setDueItems(res.data.items || [])
              } catch {
                toast.error(t('due.dismissError') || 'Could not update — try again')
              }
            }}
          >
            {t('due.undo') || 'Undo'}
          </button>
        </span>
      ), { duration: 5000 })
    } catch (error) {
      if (isOfflineWriteError(error)) {
        // Removal stands: the dismissal is queued and replays on reconnect.
        announceOfflineSaved(t)
        return
      }
      toast.error(t('due.dismissError') || 'Could not update — try again')
      try {
        const res = await dueApi.get(30)
        setDueItems(res.data.items || [])
      } catch { /* keep optimistic state; next visit refetches */ }
    }
  }, [t])

  // Is the AI assistant available on this server (Ollama enabled + configured)?
  useEffect(() => {
    let cancelled = false
    configApi.get()
      .then((r) => { if (!cancelled) setAiEnabled(!!r.data?.ai_enabled) })
      .catch(() => { if (!cancelled) setAiEnabled(false) })
    return () => { cancelled = true }
  }, [])

  // Fetch fuel prices for the user's detected location
  useEffect(() => {
    if (!userLocation) return
    
    const fetchExternalData = async () => {
      try {
        let locationName = 'London, United Kingdom'
        let countryCode = 'UK'
        try {
          const geoRes = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${userLocation.lat}&lon=${userLocation.lon}&format=json&addressdetails=1&zoom=18`,
            { headers: { 'User-Agent': 'GearCargo/1.0' } }
          )
          const geoData = await geoRes.json()
          const addr = geoData.address || {}
          // Check address fields from most specific to least specific
          // Nominatim returns different fields based on location type
          locationName = addr.suburb || 
                        addr.hamlet || 
                        addr.village || 
                        addr.town || 
                        addr.city || 
                        addr.municipality ||
                        addr.district ||
                        addr.county ||
                        addr.state ||
                        'Unknown'
          locationName += ', ' + (addr.country || 'Unknown')
          // Get country code for fuel prices (e.g., 'gb', 'de', 'fr')
          countryCode = (addr.country_code || 'uk').toUpperCase()
          // Update app currency to match the user's physical location
          setCurrencyFromCountry(countryCode)
        } catch (e) {
          console.warn('Geocoding failed:', e)
        }
        
        // Set resolved location up front so retry handlers work even if the
        // fuel-price service fails on the first attempt.
        setResolvedLocation({ countryCode, locationName, lat: userLocation.lat, lon: userLocation.lon })

        try {
          const fuelRes = await externalApi.getFuelPrices(countryCode, locationName, userLocation.lat, userLocation.lon)
          setFuelPrices(fuelRes.data)
          setFuelError(false)
          const now = Date.now()
          fuelPriceFetchedAtRef.current = now
          setFuelPriceFetchedAt(now)
        } catch (fuelErr) {
          console.error('Fuel price fetch failed:', fuelErr)
          setFuelError(true)
        }
      } catch (error) {
        console.error('Failed to fetch external data:', error)
        setFuelError(true)
      }
    }

    fetchExternalData()
  }, [userLocation])

  // Retry just the fuel-price service after a failure.
  const retryFuel = async () => {
    if (!resolvedLocation || retryingFuel) return
    setRetryingFuel(true)
    try {
      const res = await externalApi.getFuelPrices(
        resolvedLocation.countryCode, resolvedLocation.locationName,
        resolvedLocation.lat, resolvedLocation.lon,
      )
      setFuelPrices(res.data)
      setFuelError(false)
      const now = Date.now()
      fuelPriceFetchedAtRef.current = now
      setFuelPriceFetchedAt(now)
    } catch (e) {
      setFuelError(true)
    } finally {
      setRetryingFuel(false)
    }
  }

  // Manual fuel price refresh — force bypasses cache
  const handleRefreshFuelPrices = async () => {
    if (!resolvedLocation || isRefreshingFuelRef.current) return
    isRefreshingFuelRef.current = true
    setIsRefreshingFuel(true)
    try {
      const fuelRes = await externalApi.getFuelPrices(
        resolvedLocation.countryCode,
        resolvedLocation.locationName,
        resolvedLocation.lat,
        resolvedLocation.lon,
        true // force_refresh — bypass all caches
      )
      setFuelPrices(fuelRes.data)
      const now = Date.now()
      fuelPriceFetchedAtRef.current = now
      setFuelPriceFetchedAt(now)
    } catch (error) {
      console.error('Failed to refresh fuel prices:', error)
    } finally {
      setIsRefreshingFuel(false)
      isRefreshingFuelRef.current = false
    }
  }

  // Auto-refresh fuel prices every 30 min (matches backend in-memory cache TTL).
  // Pauses when the tab is hidden; resumes immediately if data is stale on tab focus.
  useEffect(() => {
    if (!resolvedLocation) return
    const INTERVAL_MS = 30 * 60 * 1000 // 30 minutes

    const doAutoRefresh = async () => {
      if (isRefreshingFuelRef.current) return
      isRefreshingFuelRef.current = true
      try {
        const res = await externalApi.getFuelPrices(
          resolvedLocation.countryCode,
          resolvedLocation.locationName,
          resolvedLocation.lat,
          resolvedLocation.lon
        )
        setFuelPrices(res.data)
        const now = Date.now()
        fuelPriceFetchedAtRef.current = now
        setFuelPriceFetchedAt(now)
      } catch (err) {
        console.warn('Auto-refresh fuel prices failed:', err)
      } finally {
        isRefreshingFuelRef.current = false
      }
    }

    const intervalId = setInterval(doAutoRefresh, INTERVAL_MS)

    // Re-fetch immediately when user returns to the tab after the data is stale
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const lastFetch = fuelPriceFetchedAtRef.current
        if (!lastFetch || Date.now() - lastFetch >= INTERVAL_MS) {
          doAutoRefresh()
        }
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      clearInterval(intervalId)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [resolvedLocation])
  
  const handleDeleteVehicle = async (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    const v = vehicles.find((x) => x.id === vehicleId)
    const name = v?.name || `${v?.make || ''} ${v?.model || ''}`.trim()
    const ok = await confirm({
      title: t('confirm.deleteVehicleTitle') || 'Delete vehicle?',
      message: (t('confirm.deleteVehicleMessage') || 'Permanently delete “{name}” and all its data (fuel, services, repairs, taxes, insurance, attachments). This cannot be undone.').replace('{name}', name),
      confirmLabel: t('common.delete') || 'Delete',
      destructive: true,
    })
    if (!ok) return

    try {
      await vehicleApi.hardDelete(vehicleId)
      setVehicles(vehicles.filter(v => v.id !== vehicleId))
    } catch (error) {
      console.error('Failed to delete vehicle:', error)
    }
  }
  
  const handleEditVehicle = (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    navigate(`/vehicles/${vehicleId}/edit`)
  }
  
  const handleViewDetails = (e, vehicleId) => {
    e.preventDefault()
    e.stopPropagation()
    navigate(`/vehicles/${vehicleId}`)
  }
  
  // Drag and drop handlers
  const handleDragStart = (e, vehicle) => {
    if (!isReorderMode) return
    setDraggedVehicle(vehicle)
    e.dataTransfer.effectAllowed = 'move'
    // Add a slight delay for visual feedback
    setTimeout(() => {
      e.target.style.opacity = '0.5'
    }, 0)
  }
  
  const handleDragEnd = (e) => {
    e.target.style.opacity = '1'
    setDraggedVehicle(null)
    setDragOverVehicle(null)
  }
  
  const handleDragOver = (e, vehicle) => {
    e.preventDefault()
    if (!draggedVehicle || draggedVehicle.id === vehicle.id) return
    setDragOverVehicle(vehicle)
  }
  
  const handleDragLeave = () => {
    setDragOverVehicle(null)
  }
  
  const handleDrop = async (e, targetVehicle) => {
    e.preventDefault()
    if (!draggedVehicle || draggedVehicle.id === targetVehicle.id) return
    
    // Reorder vehicles in local state
    const newVehicles = [...vehicles]
    const draggedIndex = newVehicles.findIndex(v => v.id === draggedVehicle.id)
    const targetIndex = newVehicles.findIndex(v => v.id === targetVehicle.id)
    
    // Remove dragged item and insert at new position
    const [removed] = newVehicles.splice(draggedIndex, 1)
    newVehicles.splice(targetIndex, 0, removed)
    
    setVehicles(newVehicles)
    setDraggedVehicle(null)
    setDragOverVehicle(null)
  }
  
  // Save the new order to backend
  const saveVehicleOrder = async () => {
    setIsSavingOrder(true)
    try {
      const order = vehicles.map(v => v.id)
      await vehicleApi.reorder(order)
      setIsReorderMode(false)
    } catch (error) {
      console.error('Failed to save vehicle order:', error)
    } finally {
      setIsSavingOrder(false)
    }
  }
  
  // Cancel reorder mode and restore original order
  const cancelReorder = async () => {
    setIsReorderMode(false)
    // Refetch to restore original order
    try {
      const vehiclesRes = await vehicleApi.getAll()
      setVehicles(vehiclesRes.data.vehicles || [])
    } catch (error) {
      console.error('Failed to refresh vehicles:', error)
    }
  }
  
  // Touch support for mobile drag-and-drop with visual feedback
  const [touchStart, setTouchStart] = useState(null)
  const [touchedVehicle, setTouchedVehicle] = useState(null)
  const [dragGhostPosition, setDragGhostPosition] = useState(null)
  const [dragGhostSize, setDragGhostSize] = useState({ width: 0, height: 0 })
  const [isDragActive, setIsDragActive] = useState(false) // Only true after threshold met
  const touchTimerRef = useRef(null)
  
  const TOUCH_HOLD_DELAY = 300 // ms to hold before drag starts
  const TOUCH_MOVE_THRESHOLD = 10 // px movement before drag activates
  
  const handleTouchStart = (e, vehicle) => {
    if (!isReorderMode) return
    
    const touch = e.touches[0]
    const card = e.currentTarget
    const rect = card.getBoundingClientRect()
    
    // Store initial touch position and card info
    setTouchStart({ 
      x: touch.clientX, 
      y: touch.clientY,
      offsetX: touch.clientX - rect.left,
      offsetY: touch.clientY - rect.top
    })
    setTouchedVehicle(vehicle)
    setDragGhostSize({ width: rect.width, height: rect.height })
    setIsDragActive(false)
    
    // Start hold timer - drag only activates after holding
    touchTimerRef.current = setTimeout(() => {
      setIsDragActive(true)
      setDragGhostPosition({ x: touch.clientX, y: touch.clientY })
      // Vibration feedback if available
      if (navigator.vibrate) navigator.vibrate(50)
    }, TOUCH_HOLD_DELAY)
  }
  
  const handleTouchMove = (e, vehicle) => {
    if (!isReorderMode || !touchedVehicle || !touchStart) return
    
    const touch = e.touches[0]
    const dx = Math.abs(touch.clientX - touchStart.x)
    const dy = Math.abs(touch.clientY - touchStart.y)
    
    // If moved before hold timer finished, cancel drag (it was a scroll)
    if (!isDragActive && (dx > TOUCH_MOVE_THRESHOLD || dy > TOUCH_MOVE_THRESHOLD)) {
      clearTimeout(touchTimerRef.current)
      setTouchStart(null)
      setTouchedVehicle(null)
      return
    }
    
    // Only process drag if active
    if (!isDragActive) return
    
    e.preventDefault() // Prevent scrolling only when actually dragging
    
    // Update ghost position to follow finger
    setDragGhostPosition({ x: touch.clientX, y: touch.clientY })
    
    // Hide the ghost temporarily to find element underneath
    const ghostEl = document.getElementById('drag-ghost')
    if (ghostEl) ghostEl.style.display = 'none'
    
    const element = document.elementFromPoint(touch.clientX, touch.clientY)
    
    // Show the ghost again
    if (ghostEl) ghostEl.style.display = 'block'
    
    const vehicleCard = element?.closest('[data-vehicle-id]')
    
    if (vehicleCard) {
      const targetId = parseInt(vehicleCard.dataset.vehicleId)
      const targetVehicle = vehicles.find(v => v.id === targetId)
      if (targetVehicle && targetVehicle.id !== touchedVehicle.id) {
        setDragOverVehicle(targetVehicle)
      }
    } else {
      setDragOverVehicle(null)
    }
  }
  
  const handleTouchEnd = () => {
    // Clear hold timer
    clearTimeout(touchTimerRef.current)
    
    if (isDragActive && touchedVehicle && dragOverVehicle && touchedVehicle.id !== dragOverVehicle.id) {
      // Perform the reorder
      const newVehicles = [...vehicles]
      const draggedIndex = newVehicles.findIndex(v => v.id === touchedVehicle.id)
      const targetIndex = newVehicles.findIndex(v => v.id === dragOverVehicle.id)
      
      const [removed] = newVehicles.splice(draggedIndex, 1)
      newVehicles.splice(targetIndex, 0, removed)
      
      setVehicles(newVehicles)
    }
    
    setTouchStart(null)
    setTouchedVehicle(null)
    setDragOverVehicle(null)
    setDragGhostPosition(null)
    setIsDragActive(false)
  }
  
  if (isLoading) {
    return (
      <div className="p-4 lg:p-6 space-y-4">
        <div className="skeleton h-28 rounded-xl" />
        <div className="skeleton h-8 w-48 rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton h-64 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }
  
  return (
    <div className="p-4 lg:p-6 pb-24 lg:pb-6">
      {/* AI Assistant banner — only when the server has an Ollama integration */}
      {aiEnabled && (
      <button
        type="button"
        onClick={() => setChatOpen(true)}
        className="w-full mb-4 flex items-center gap-3 text-left rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3 hover:border-[var(--color-accent)] hover:bg-[var(--color-bg-tertiary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        aria-haspopup="dialog"
      >
        <span className="shrink-0 w-10 h-10 rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)] flex items-center justify-center" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="8" width="18" height="12" rx="2" /><path d="M12 8V5M9 3h6M8 13h.01M16 13h.01M9 17h6" />
          </svg>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-2xs font-semibold uppercase tracking-wide text-[var(--color-accent)]">
            {t('dashboard.assistantEyebrow') || 'AI Assistant'}
          </span>
          <span className="block text-sm text-[var(--color-text-primary)] truncate">
            {t('dashboard.assistantPrompt') || 'How can I help you today?'}
          </span>
        </span>
        <span className="shrink-0 inline-flex items-center gap-1 text-sm font-medium text-[var(--color-accent)]">
          {t('dashboard.assistantCta') || 'Chat'}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </span>
      </button>
      )}

      {aiEnabled && <ChatModal open={chatOpen} onClose={() => setChatOpen(false)} vehicles={vehicles} />}

      {/* Fuel Prices Widget — full-width banner */}
      <div className="mb-6">
        <FuelPricesWidget fuelPrices={fuelPrices} currency={currency} t={t} onRefresh={handleRefreshFuelPrices} isRefreshing={isRefreshingFuel} lastAutoUpdate={fuelPriceFetchedAt}
          error={fuelError && !fuelDismissed}
          onRetry={retryFuel}
          retrying={retryingFuel}
          onDismiss={() => setFuelDismissed(true)}
        />
      </div>

      {/* Your Garage Section */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold">{t('dashboard.yourGarage')}</h2>
          {vehicles.length > 1 && !isReorderMode && (
            <button
              onClick={() => setIsReorderMode(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
              title={t('dashboard.reorderVehicles')}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
              </svg>
              <span className="hidden sm:inline">{t('dashboard.reorder')}</span>
            </button>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {isReorderMode ? (
            <>
              <button
                onClick={cancelReorder}
                className="px-3 py-1.5 text-sm rounded-lg bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] transition-colors"
                disabled={isSavingOrder}
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={saveVehicleOrder}
                className="px-3 py-1.5 text-sm rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white transition-colors flex items-center gap-1.5"
                disabled={isSavingOrder}
              >
                {isSavingOrder ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>{t('common.saving')}</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <span>{t('common.save')}</span>
                  </>
                )}
              </button>
            </>
          ) : (
            <Link 
              to="/vehicles/add" 
              className="btn btn-primary flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              {t('dashboard.addVehicle')}
            </Link>
          )}
        </div>
      </div>
      
      {/* Reorder Mode Instructions */}
      {isReorderMode && (
        <div className="mb-4 p-3 rounded-lg bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20">
          <p className="text-sm text-[var(--color-text-secondary)] flex items-center gap-2">
            <svg className="w-5 h-5 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {t('dashboard.reorderInstructions')}
          </p>
        </div>
      )}
      
      {/* Vehicles Grid */}
      {vehiclesError && vehicles.length === 0 ? (
        <div
          role="status"
          aria-live="polite"
          className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] text-center py-16 px-4"
        >
          <svg className="w-10 h-10 mx-auto mb-4 text-[var(--color-text-muted)] animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <h3 className="text-lg font-medium mb-2">{t('dashboard.startingUpTitle')}</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-6 max-w-md mx-auto">
            {t('dashboard.startingUpMessage')}
          </p>
          <button
            type="button"
            onClick={handleRetryVehicles}
            disabled={retryingVehicles}
            aria-busy={retryingVehicles}
            className="btn btn-primary disabled:opacity-60 disabled:cursor-wait"
          >
            {t('dashboard.startingUpRetry')}
          </button>
        </div>
      ) : vehicles.length === 0 ? (
        <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] text-center py-16">
          <span className="text-6xl mb-4 block">🚗</span>
          <h3 className="text-lg font-medium mb-2">{t('dashboard.noVehicles')}</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-6">
            {t('dashboard.addFirstVehicle')}
          </p>
          <Link to="/vehicles/add" className="btn btn-primary">
            <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            {t('dashboard.addVehicle')}
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
          {vehicles.map((vehicle, index) => (
            <div
              key={vehicle.id}
              data-vehicle-id={vehicle.id}
              draggable={isReorderMode}
              onDragStart={(e) => handleDragStart(e, vehicle)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, vehicle)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, vehicle)}
              onTouchStart={(e) => handleTouchStart(e, vehicle)}
              onTouchMove={(e) => handleTouchMove(e, vehicle)}
              onTouchEnd={handleTouchEnd}
              className={`
                group bg-[var(--color-bg-card)] rounded-xl border overflow-hidden transition-all duration-300
                ${isReorderMode 
                  ? 'cursor-grab active:cursor-grabbing border-dashed border-2 border-[var(--color-accent)]/50' 
                  : 'border-[var(--color-border)] hover:border-[var(--color-accent)] hover:shadow-lg hover:shadow-[var(--color-accent)]/10'}
                ${dragOverVehicle?.id === vehicle.id ? 'ring-2 ring-[var(--color-accent)] scale-[1.02]' : ''}
                ${draggedVehicle?.id === vehicle.id ? 'opacity-50' : ''}
                ${touchedVehicle?.id === vehicle.id ? 'ring-2 ring-[var(--color-accent)]' : ''}
              `}
            >
              {/* Drag Handle - only shown in reorder mode */}
              {isReorderMode && (
                <div className="absolute top-2 left-2 z-10 w-8 h-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center text-white shadow-lg">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 8h16M4 16h16" />
                  </svg>
                </div>
              )}
              
              {/* Order Number Badge - only shown in reorder mode */}
              {isReorderMode && (
                <div className="absolute top-2 right-2 z-10 w-6 h-6 rounded-full bg-[var(--color-bg-card)] border border-[var(--color-border)] flex items-center justify-center text-xs font-bold text-[var(--color-text-secondary)]">
                  {index + 1}
                </div>
              )}
              
              {/* Make the card clickable only when not in reorder mode */}
              {isReorderMode ? (
                <>
                  {/* Vehicle Image */}
                  <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
                    {vehicle.photo_url || vehicle.photo ? (
                      <img 
                        src={vehicle.photo_url || vehicle.photo} 
                        alt={vehicle.name}
                        className="w-full h-full object-cover pointer-events-none"
                        draggable={false}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                        <span className="text-6xl opacity-30">🚗</span>
                      </div>
                    )}
                  </div>
                  
                  {/* Vehicle Info */}
                  <div className="p-4">
                    <h3 className="text-base font-bold mb-0.5 text-[var(--color-text-primary)]">{vehicle.name}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                      {vehicle.make} {vehicle.model} ({vehicle.year})
                    </p>
                    
                    {vehicle.license_plate && (
                      <span className="inline-block px-2.5 py-1 text-xs font-bold rounded bg-[var(--color-accent)] text-white mb-2">
                        {vehicle.license_plate}
                      </span>
                    )}
                    
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {t('dashboard.odometer')}: <span className="text-[var(--color-text-primary)] font-semibold">
                        {vehicle.current_mileage?.toLocaleString() || 0} {vehicle.distance_unit || 'km'}
                      </span>
                    </p>
                  </div>
                </>
              ) : (
                <Link 
                  to={`/vehicles/${vehicle.id}`}
                  className="block"
                >
                  {/* Vehicle Image */}
                  <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
                    {vehicle.photo_url || vehicle.photo ? (
                      <img 
                        src={vehicle.photo_url || vehicle.photo} 
                        alt={vehicle.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                        <span className="text-6xl opacity-30">🚗</span>
                      </div>
                    )}
                    
                    {/* Action Buttons Overlay */}
                    <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-1 group-hover:translate-y-0">
                      <button 
                        onClick={(e) => handleEditVehicle(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-[var(--color-accent)] transition-colors"
                        title="Edit"
                      >
                        <span className="material-icons-outlined text-sm">edit</span>
                      </button>
                      <button 
                        onClick={(e) => handleViewDetails(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-[var(--color-accent)] transition-colors"
                        title="Details"
                      >
                        <span className="material-icons-outlined text-sm">list</span>
                      </button>
                      <button 
                        onClick={(e) => handleDeleteVehicle(e, vehicle.id)}
                        className="w-8 h-8 rounded-lg bg-black/60 backdrop-blur-md flex items-center justify-center text-white hover:bg-red-500 transition-colors"
                        title="Delete"
                      >
                        <span className="material-icons-outlined text-sm">delete</span>
                      </button>
                    </div>
                    
                    {/* Insurance Status Badges */}
                    <div className="absolute bottom-2 left-2 flex items-center gap-1">
                      {vehicleInsurance[vehicle.id]?.expiring ? (
                        <div 
                          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-500/90 backdrop-blur-sm text-white text-xs font-medium shadow-lg"
                          title={`${t('dashboard.insuranceExpiring') || 'Insurance expiring'}: ${formatDate(vehicleInsurance[vehicle.id].expiring.end_date)}`}
                        >
                          <span className="material-icons-outlined text-sm">warning</span>
                          <span className="hidden sm:inline">{t('dashboard.expiringSoon') || 'Expiring'}</span>
                        </div>
                      ) : vehicleInsurance[vehicle.id]?.active ? (
                        <div 
                          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-green-500/90 backdrop-blur-sm text-white text-xs font-medium shadow-lg"
                          title={t('dashboard.insuranceActive') || 'Insurance active'}
                        >
                          <span className="material-icons-outlined text-sm">verified_user</span>
                          <span className="hidden sm:inline">{t('dashboard.insured') || 'Insured'}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  
                  {/* Vehicle Info */}
                  <div className="p-4">
                    <h3 className="text-base font-bold mb-0.5 text-[var(--color-text-primary)]">{vehicle.name}</h3>
                    <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                      {vehicle.make} {vehicle.model} ({vehicle.year})
                    </p>
                    
                    {vehicle.license_plate && (
                      <span className="inline-block px-2.5 py-1 text-xs font-bold rounded bg-[var(--color-accent)] text-white mb-2">
                        {vehicle.license_plate}
                      </span>
                    )}
                    
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {t('dashboard.odometer')}: <span className="text-[var(--color-text-primary)] font-semibold">
                        {vehicle.current_mileage?.toLocaleString() || 0} {vehicle.distance_unit || 'km'}
                      </span>
                    </p>
                  </div>
                </Link>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Coming up — unified "Due & Expiring" surface (F4), full-width above the feed.
          Gated on having items so an all-caught-up fleet stays uncluttered. */}
      {vehicles.length > 0 && (dueLoading || dueItems.length > 0) && (
        <div className="mt-8">
          <DueSoon
            items={dueItems}
            loading={dueLoading}
            error={dueError}
            t={t}
            onDismiss={handleDismissDue}
          />
        </div>
      )}

      {/* Recent Transactions — full-width, below the garage */}
      {vehicles.length > 0 && (
        <div className="mt-8">
          <RecentTransactions
            transactions={recentTx}
            loading={recentTxLoading}
            error={recentTxError}
            t={t}
            formatCurrency={formatCurrency}
          />
        </div>
      )}

      {/* Drag Ghost for Touch Devices */}
      {touchedVehicle && dragGhostPosition && (
        <div
          id="drag-ghost"
          className="fixed pointer-events-none z-50 transition-transform duration-75"
          style={{
            left: dragGhostPosition.x - (touchStart?.offsetX || dragGhostSize.width / 2),
            top: dragGhostPosition.y - (touchStart?.offsetY || 40),
            width: dragGhostSize.width,
            transform: 'rotate(-2deg) scale(1.02)',
          }}
        >
          <div className="bg-[var(--color-bg-card)] rounded-xl border-2 border-[var(--color-accent)] shadow-2xl shadow-[var(--color-accent)]/30 overflow-hidden opacity-90">
            {/* Drag indicator */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 bg-[var(--color-accent)] text-white text-xs px-3 py-1 rounded-full font-medium shadow-lg flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
              </svg>
              {t('dashboard.dragging') || 'Moving...'}
            </div>
            
            {/* Vehicle Image */}
            <div className="relative aspect-[16/10] bg-[var(--color-bg-tertiary)] overflow-hidden">
              {touchedVehicle.photo_url || touchedVehicle.photo ? (
                <img 
                  src={touchedVehicle.photo_url || touchedVehicle.photo} 
                  alt={touchedVehicle.name}
                  className="w-full h-full object-cover"
                  draggable={false}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-[var(--color-bg-secondary)] to-[var(--color-bg-tertiary)]">
                  <span className="text-5xl opacity-30">🚗</span>
                </div>
              )}
            </div>
            
            {/* Vehicle Info */}
            <div className="p-3">
              <h3 className="text-sm font-bold text-[var(--color-text-primary)]">{touchedVehicle.name}</h3>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {touchedVehicle.make} {touchedVehicle.model}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
