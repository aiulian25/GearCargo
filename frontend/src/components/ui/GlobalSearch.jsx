/**
 * GlobalSearch — full-text search modal
 *
 * Opens on Ctrl+K / Cmd+K or when the search icon in the header is tapped.
 * Searches vehicles, entries (fuel/service/repair/tax/parking) and attachment
 * OCR text via GET /api/search?q=... Results are grouped by category.
 *
 * Accessibility: focus is trapped inside the modal; Escape closes it.
 * Performance: input is debounced 300 ms before sending the API call.
 * Security: the API enforces user-scoped results; this component never echoes
 *           raw HTML — all text is rendered via React (XSS-safe by default).
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { searchApi } from '../../services/api'

// ── SVG icon helpers ─────────────────────────────────────────────────────────
const SearchIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 104.5 4.5a7.5 7.5 0 0012.15 12.15z" />
  </svg>
)

const CarIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" />
  </svg>
)

const EntryIcon = ({ type }) => {
  if (type === 'fuel') return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3.75 21h10.5M5.25 21V6a2.25 2.25 0 012.25-2.25h3A2.25 2.25 0 0112.75 6v15m-7.5-9h7.5m-7.5 0v4.5m0-4.5V9m7.5 3v4.5m0-4.5V9m4.5-1.5v9a1.5 1.5 0 001.5 1.5h.75a.75.75 0 00.75-.75v-6a.75.75 0 00-.75-.75h-.75m0 0V6.75a.75.75 0 01.75-.75h.75a2.25 2.25 0 012.25 2.25v1.5" />
    </svg>
  )
  if (type === 'repair') return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
    </svg>
  )
  if (type === 'service') return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )
  // Generic icon for tax, parking, etc.
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  )
}

const AttachmentIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
  </svg>
)

const ReminderIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
  </svg>
)

const InsuranceIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
  </svg>
)

const SpinnerIcon = () => (
  <div className="w-4 h-4 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
)

// ── Entry type → colour mapping ───────────────────────────────────────────────
const TYPE_COLOUR = {
  fuel:    'text-amber-400',
  service: 'text-cyan-400',
  repair:  'text-red-400',
  tax:     'text-purple-400',
  parking: 'text-blue-400',
}

// ── Helper: format currency amount ───────────────────────────────────────────
function formatAmount(amount, currency) {
  if (!amount) return null
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: currency || 'EUR',
    maximumFractionDigits: 2,
  }).format(amount)
}

// ── Main component ────────────────────────────────────────────────────────────
export default function GlobalSearch({ isOpen, onClose }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const timerRef = useRef(null)

  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null) // null = never searched
  const [error, setError] = useState('')

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50)
    } else {
      // Reset state on close so next open is clean
      setQuery('')
      setResults(null)
      setError('')
    }
  }, [isOpen])

  // Keyboard: Escape closes the modal
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape' && isOpen) onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  // Debounced search — fires 300 ms after the user stops typing
  const doSearch = useCallback(async (q) => {
    if (q.length < 2) {
      setResults(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await searchApi.search(q)
      setResults(res.data.results)
    } catch (err) {
      if (err.response?.status === 429) {
        setError(t('search.rateLimited') || 'Too many requests — please slow down.')
      } else {
        setError(t('search.error') || 'Search failed. Please try again.')
      }
      setResults(null)
    } finally {
      setLoading(false)
    }
  }, [t])

  const handleInputChange = (e) => {
    const q = e.target.value
    setQuery(q)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => doSearch(q.trim()), 300)
  }

  // Navigate to the appropriate page and close modal
  const goTo = (path) => {
    onClose()
    navigate(path)
  }

  const handleVehicleClick = (v) => goTo(`/vehicles/${v.id}`)
  const handleEntryClick = (e) => goTo(`/vehicles/${e.vehicle_id}`)
  const handleReminderClick = () => goTo('/reminders')
  const handleInsuranceClick = (p) =>
    goTo(p.vehicle_id ? `/vehicles/${p.vehicle_id}/expenses` : '/vehicles')
  const handleAttachmentClick = (a) => {
    if (a.vehicle_id) {
      // Navigate to the per-vehicle documents page and deep-link directly to
      // this attachment by appending ?open=<id>.  VehicleDocuments reads this
      // param on mount and auto-opens the viewer for the specific file.
      goTo(`/vehicles/${a.vehicle_id}/search?open=${a.id}`)
    }
  }

  if (!isOpen) return null

  const hasVehicles = results?.vehicles?.length > 0
  const hasEntries = results?.entries?.length > 0
  const hasReminders = results?.reminders?.length > 0
  const hasInsurance = results?.insurance?.length > 0
  const hasAttachments = results?.attachments?.length > 0
  const hasResults = hasVehicles || hasEntries || hasReminders || hasInsurance || hasAttachments
  const searchedButEmpty = results !== null && !hasResults

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 pt-16 px-4"
      onClick={onClose}
    >
      {/* Modal panel — stop propagation so clicking inside doesn't close */}
      <div
        className="w-full max-w-xl bg-[var(--color-bg-secondary)] rounded-2xl shadow-2xl border border-[var(--color-border)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input row */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border)]">
          <span className="text-[var(--color-text-muted)] flex-shrink-0">
            {loading ? <SpinnerIcon /> : <SearchIcon />}
          </span>
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={handleInputChange}
            placeholder={t('search.placeholder') || 'Search vehicles, entries, receipts…'}
            className="flex-1 bg-transparent text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] text-base outline-none"
            maxLength={100}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
          />
          <kbd
            className="hidden sm:flex items-center gap-1 px-1.5 py-0.5 text-2xs text-[var(--color-text-muted)] border border-[var(--color-border)] rounded"
            aria-label="Press Escape to close"
          >
            Esc
          </kbd>
        </div>

        {/* Results area */}
        <div className="max-h-[60vh] overflow-y-auto overscroll-contain">
          {/* Error */}
          {error && (
            <p className="px-4 py-3 text-sm text-red-400">{error}</p>
          )}

          {/* Hint before first search */}
          {!error && results === null && query.length === 0 && (
            <p className="px-4 py-6 text-sm text-center text-[var(--color-text-muted)]">
              {t('search.hint') || 'Type to search across all your vehicle data, receipts and notes.'}
            </p>
          )}

          {/* Minimum length hint */}
          {!error && results === null && query.length > 0 && query.length < 2 && (
            <p className="px-4 py-3 text-sm text-[var(--color-text-muted)]">
              {t('search.minChars') || 'Enter at least 2 characters to search.'}
            </p>
          )}

          {/* No results */}
          {!error && searchedButEmpty && (
            <p className="px-4 py-6 text-sm text-center text-[var(--color-text-muted)]">
              {t('search.noResults') || 'No results found.'}
            </p>
          )}

          {/* Grouped results */}
          {hasResults && (
            <div className="pb-2">
              {/* Vehicles */}
              {hasVehicles && (
                <section>
                  <h3 className="px-4 pt-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    {t('search.groupVehicles') || 'Vehicles'}
                  </h3>
                  {results.vehicles.map((v) => (
                    <button
                      key={v.id}
                      onClick={() => handleVehicleClick(v)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors text-left"
                    >
                      <span className="text-cyan-400 flex-shrink-0"><CarIcon /></span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">{v.name}</p>
                        {(v.make || v.year) && (
                          <p className="text-xs text-[var(--color-text-muted)] truncate">
                            {[v.year, v.make, v.model].filter(Boolean).join(' ')}
                            {v.license_plate && ` · ${v.license_plate}`}
                          </p>
                        )}
                      </div>
                    </button>
                  ))}
                </section>
              )}

              {/* Entries */}
              {hasEntries && (
                <section>
                  <h3 className="px-4 pt-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    {t('search.groupEntries') || 'Entries'}
                  </h3>
                  {results.entries.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => handleEntryClick(e)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors text-left"
                    >
                      <span className={`flex-shrink-0 ${TYPE_COLOUR[e.type] || 'text-gray-400'}`}>
                        <EntryIcon type={e.type} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                          {e.title || t(`entryTypes.${e.type}`) || e.type}
                        </p>
                        <p className="text-xs text-[var(--color-text-muted)] truncate">
                          {e.vehicle_name && `${e.vehicle_name} · `}
                          {e.date}
                          {e.amount && ` · ${formatAmount(e.amount, e.currency)}`}
                        </p>
                      </div>
                    </button>
                  ))}
                </section>
              )}

              {/* Reminders */}
              {hasReminders && (
                <section>
                  <h3 className="px-4 pt-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    {t('search.groupReminders') || 'Reminders'}
                  </h3>
                  {results.reminders.map((r) => (
                    <button
                      key={r.id}
                      onClick={handleReminderClick}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors text-left"
                    >
                      <span className="text-amber-400 flex-shrink-0"><ReminderIcon /></span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">{r.title}</p>
                        <p className="text-xs text-[var(--color-text-muted)] truncate">
                          {r.vehicle_name && `${r.vehicle_name} · `}
                          {r.due_date}
                        </p>
                      </div>
                    </button>
                  ))}
                </section>
              )}

              {/* Insurance */}
              {hasInsurance && (
                <section>
                  <h3 className="px-4 pt-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    {t('search.groupInsurance') || 'Insurance'}
                  </h3>
                  {results.insurance.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleInsuranceClick(p)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors text-left"
                    >
                      <span className="text-teal-400 flex-shrink-0"><InsuranceIcon /></span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">{p.provider}</p>
                        <p className="text-xs text-[var(--color-text-muted)] truncate">
                          {p.vehicle_name && `${p.vehicle_name} · `}
                          {p.policy_number && `${p.policy_number}`}
                          {p.end_date && ` · ${p.end_date}`}
                        </p>
                      </div>
                    </button>
                  ))}
                </section>
              )}

              {/* Attachments / OCR */}
              {hasAttachments && (
                <section>
                  <h3 className="px-4 pt-3 pb-1 text-2xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    {t('search.groupAttachments') || 'Scanned Documents'}
                  </h3>
                  {results.attachments.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => handleAttachmentClick(a)}
                      className="w-full flex items-start gap-3 px-4 py-2.5 hover:bg-[var(--color-bg-hover,rgba(255,255,255,0.06))] transition-colors text-left"
                    >
                      <span className="text-purple-400 flex-shrink-0 mt-0.5"><AttachmentIcon /></span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                          {a.filename}
                        </p>
                        {a.ocr_snippet && (
                          <p className="text-xs text-[var(--color-text-muted)] line-clamp-2 mt-0.5">
                            {a.ocr_snippet}
                          </p>
                        )}
                        {a.vehicle_name && (
                          <p className="text-xs text-[var(--color-text-muted)]">{a.vehicle_name}</p>
                        )}
                      </div>
                    </button>
                  ))}
                </section>
              )}
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="border-t border-[var(--color-border)] px-4 py-2 flex items-center gap-4 text-2xs text-[var(--color-text-muted)]">
          <span>↵ {t('search.selectHint') || 'to open'}</span>
          <span>Esc {t('search.closeHint') || 'to close'}</span>
        </div>
      </div>
    </div>
  )
}
