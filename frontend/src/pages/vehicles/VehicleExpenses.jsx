import { localDate } from '../../utils/dateFormat'
import useExpenseFilters from '../../hooks/useExpenseFilters'
import useExpenseRecords from '../../hooks/useExpenseRecords'
import ExpensePagination from '../../components/ui/ExpensePagination'
import useExpenseSummary from '../../hooks/useExpenseSummary'
import FinancialBasis from '../../components/ui/FinancialBasis'
import { mutationOptions } from '../../utils/mutationProtocol'
import { useState, useEffect, useMemo, useId, Fragment } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { vehicleApi, fuelApi, serviceApi, repairApi, taxApi, reminderApi, insuranceApi, parkingApi, consumableApi } from '../../services/api'
import api from '../../services/api'
import toast from 'react-hot-toast'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { litersToDisplayVolume, pricePerLiterToDisplay, volumeUnitLabel } from '../../utils/fuelEconomy'
import { useDateFormat } from '../../hooks/useDateFormat'
import { Skeleton, SkeletonScreen } from '../../components/ui/Skeleton'
import AttachmentViewer from '../../components/ui/AttachmentViewer'

// Icons
const Icons = {
  arrowBack: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 19l-7-7 7-7"/>
    </svg>
  ),
  fuel: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17"/><path d="M15 22H3"/><path d="M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3"/>
      <rect x="6" y="6" width="6" height="5" rx="1"/>
    </svg>
  ),
  service: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  ),
  tax: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 18V6"/>
    </svg>
  ),
  parking: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/>
    </svg>
  ),
  repair: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  todo: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
  reminder: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  delete: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
  attachment: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
    </svg>
  ),
  eye: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ),
  edit: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  download: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  cancelRecurring: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
    </svg>
  ),
  scan: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
      <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
    </svg>
  ),
  chevronDown: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  copy: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  ),
  phone: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
    </svg>
  ),
  mail: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
      <polyline points="22,6 12,13 2,6"/>
    </svg>
  ),
}

// Donut Chart Component
const DonutChart = ({ data, centerText, centerSubtext, currency }) => {
  const total = data.reduce((sum, item) => sum + item.value, 0)
  let currentAngle = -90 // Start from top
  
  const segments = data.map((item, index) => {
    const percentage = total > 0 ? (item.value / total) * 100 : 0
    const angle = (percentage / 100) * 360
    const startAngle = currentAngle
    currentAngle += angle
    
    // Calculate SVG arc path
    const startRad = (startAngle * Math.PI) / 180
    const endRad = ((startAngle + angle) * Math.PI) / 180
    const largeArc = angle > 180 ? 1 : 0
    
    const x1 = 100 + 80 * Math.cos(startRad)
    const y1 = 100 + 80 * Math.sin(startRad)
    const x2 = 100 + 80 * Math.cos(endRad)
    const y2 = 100 + 80 * Math.sin(endRad)
    
    return {
      ...item,
      percentage,
      path: percentage > 0 ? `M 100 100 L ${x1} ${y1} A 80 80 0 ${largeArc} 1 ${x2} ${y2} Z` : '',
    }
  })

  return (
    <div className="relative">
      <svg aria-hidden="true" viewBox="0 0 200 200" className="w-full max-w-[280px] mx-auto">
        {/* Background circle when no data */}
        {total === 0 && (
          <circle cx="100" cy="100" r="80" fill="var(--color-bg-tertiary)" />
        )}
        {segments.map((segment, i) => (
          segment.path && (
            <path
              key={i}
              d={segment.path}
              fill={segment.color}
              className="transition-all duration-300 hover:opacity-80"
            />
          )
        ))}
        {/* Inner circle for donut effect */}
        <circle cx="100" cy="100" r="50" fill="var(--color-bg-secondary)" />
        {/* Center text */}
        <text x="100" y="95" textAnchor="middle" fill="var(--color-text-secondary)" className="text-[10px]">
          {centerText}
        </text>
        <text x="100" y="115" textAnchor="middle" fill="var(--color-text-primary)" className="text-sm font-bold">
          {centerSubtext}
        </text>
      </svg>
      
      {/* Legend */}
      <div className="mt-4 space-y-2">
        {data.map((item, i) => (
          <div key={i} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
              <span className="text-(--color-text-primary)">{item.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-(--color-text-primary)">{item.value.toFixed(2)} {currency}</span>
              <span className="text-(--color-text-secondary)">({((item.value / (total || 1)) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}


// Monthly filters and a readable equivalent of the chart's complete totals.
const BarChart = ({ data, categories, title, onMonthClick, selectedMonth, hintText, currency, year }) => {
  const { monthNames, monthNamesShort } = useDateFormat()
  const { t, language } = useTranslation()
  const chartId = useId()
  const maxValue = Math.max(...data.map(d => d.total), 1)
  const formatTotal = value => `${new Intl.NumberFormat(language || 'en', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value)} ${currency || t('financial.unknownCurrency')}`
  const months = monthNames.map((name, i) => ({ name, shortName: monthNamesShort[i],
    total: data.find(d => d.month === i + 1)?.total ?? 0 }))
  const selection = selectedMonth === null
    ? t('expenses.showingYear').replace('{year}', year)
    : t('expenses.showingMonth').replace('{month}', monthNames[selectedMonth]).replace('{year}', year)

  return (
    <section className="h-full flex flex-col" aria-labelledby={`${chartId}-title`}>
      <h3 id={`${chartId}-title`} className="text-(--color-text-primary) text-sm font-medium mb-1 text-center">{title}</h3>
      <p id={`${chartId}-hint`} className="text-xs text-center text-(--color-text-secondary) mb-3">{hintText}</p>

      {/* Keep each month a usable touch target; focus scrolls it into view on narrow screens. */}
      <div className="overflow-x-auto px-1 py-2">
        <div role="group" aria-labelledby={`${chartId}-title`} aria-describedby={`${chartId}-hint`}
          className="flex items-end gap-2 min-w-max">
          {months.map((month, i) => {
            const height = (month.total / maxValue) * 100
            const isSelected = selectedMonth === i
            const label = t('expenses.monthFilterLabel').replace('{month}', month.name)
              .replace('{year}', year).replace('{total}', formatTotal(month.total))
            return (
              <button
                key={i}
                type="button"
                className={`flex-1 min-w-11 min-h-11 flex flex-col items-center rounded-sm px-1 py-1 text-(--color-text-primary)
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-text-primary)
                  ${isSelected ? 'bg-(--color-bg-tertiary) font-semibold' : 'hover:bg-(--color-bg-tertiary)'}`}
                onClick={() => onMonthClick(i)}
                aria-pressed={isSelected}
                aria-label={label}
              >
                <span aria-hidden="true" className="w-full flex flex-col justify-end h-32 relative">
                  <span className="w-full rounded-t border-(--color-text-primary)"
                    style={{ height: `${Math.max(height, 0)}%`, minHeight: month.total > 0 ? '4px' : '0',
                      borderWidth: month.total > 0 ? '1px' : '0',
                      background: month.total > 0 ? 'linear-gradient(to top, #22c55e, #84cc16, #facc15, #f97316, #ef4444)' : 'transparent' }} />
                </span>
                <span aria-hidden="true" className={`text-xs mt-1 ${isSelected ? 'underline underline-offset-4' : ''}`}>
                  {month.shortName}
                </span>
              </button>
            )
          })}
        </div>
      </div>
      <button type="button" onClick={() => onMonthClick(null)} aria-pressed={selectedMonth === null}
        className="self-start min-h-11 px-3 mt-2 rounded-sm text-sm text-(--color-text-primary) underline underline-offset-2
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-text-primary)">
        {t('expenses.fullYear')}
      </button>
      <p role="status" className="text-xs text-(--color-text-secondary) mt-1">{selection}</p>

      <details className="mt-3 text-sm text-(--color-text-primary)">
        <summary className="min-h-11 py-3 px-1 cursor-pointer rounded-sm
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-text-primary)">
          {t('expenses.monthlyTotals')}
        </summary>
        <table className="w-full text-left text-sm">
          <caption className="text-left py-2 text-(--color-text-secondary)">
            {t('expenses.monthlyTotalsYear').replace('{year}', year)}
          </caption>
          <thead><tr><th scope="col" className="py-2">{t('expenses.monthColumn')}</th>
            <th scope="col" className="py-2 text-right">{t('expenses.totalColumn')}</th></tr></thead>
          <tbody>{months.map((month, i) => <tr key={i}>
            <th scope="row" className="py-1 font-normal">{month.name}</th>
            <td className="py-1 text-right tabular-nums">{formatTotal(month.total)}</td>
          </tr>)}</tbody>
        </table>
      </details>

      <div className="flex flex-wrap gap-2 mt-4 justify-center">
        {categories.map((cat, i) => (
          <span key={i} className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-xs font-medium bg-(--color-bg-tertiary) text-(--color-text-primary)">
            <span aria-hidden="true" className="w-2 h-2 rounded-full" style={{ backgroundColor: cat.color }} />
            {cat.label}
          </span>
        ))}
      </div>
    </section>
  )
}

// Tab colors matching VehicleDetail
const tabColors = {
  fuel: 'bg-amber-500',
  service: 'bg-blue-500',
  tax: 'bg-rose-500',
  parking: 'bg-purple-500',
  repair: 'bg-red-500',
  insurance: 'bg-emerald-500',
  todo: 'bg-indigo-500',
  reminder: 'bg-green-500',
}

// Tab Button Component - matching VehicleDetail style
const TabButton = ({ active, icon, label, count, onClick, tabId }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
      active 
        ? `${tabColors[tabId] || 'bg-(--color-accent)'} text-white` 
        : 'bg-(--color-bg-tertiary) text-(--color-text-primary) hover:bg-(--color-bg-secondary)'
    }`}
  >
    <span className={active ? 'text-white' : 'text-(--color-text-secondary)'}>{icon}</span>
    <span>{label}</span>
    {count !== undefined && count > 0 && (
      <span className={`text-xs ${active ? 'text-white/80' : 'text-(--color-text-muted)'}`}>({count})</span>
    )}
  </button>
)


// F34 — badge for recurring series templates: "Monthly · next 01 Aug". Makes
// the template visually distinct from generated occurrences so users know
// which row's "Stop repeating" ends the series.
function RecurringChip({ entry, t }) {
  const { formatDate } = useDateFormat()
  if (!entry.recurring) return null
  const freq = entry.recurrence_type
    ? (t(`recurring.${entry.recurrence_type}`) || entry.recurrence_type)
    : (t('addTax.recurring') || 'Recurring')
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 rounded-full text-xs whitespace-nowrap">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M17 2.1l4 4-4 4"/><path d="M3 12.2v-2a4 4 0 0 1 4-4h12.8"/>
        <path d="M7 21.9l-4-4 4-4"/><path d="M21 11.8v2a4 4 0 0 1-4 4H4.2"/>
      </svg>
      {freq}
      {entry.next_due_date &&
        ` · ${(t('recurring.nextOn') || 'next {date}').replace('{date}', formatDate(entry.next_due_date))}`}
    </span>
  )
}

export default function VehicleExpenses() {
  const { formatDate, monthNames, monthNamesShort } = useDateFormat()
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const formatCurrency = (amount, currency) => `${Number(amount ?? 0).toFixed(2)} ${currency || t('financial.unknownCurrency')}`
  const { user } = useAuth()  // F27 — volume unit preference
  
  const [vehicle, setVehicle] = useState(null)
  const [loading, setLoading] = useState(true)
  const { tab: activeTab, setTab: setActiveTab, year: selectedYear, setYear: setSelectedYear,
    month, setMonth, page, setPage } = useExpenseFilters()
  const selectedMonth = month == null ? null : month - 1
  const setSelectedMonth = index => setMonth(index == null ? null : index + 1)
  const [refreshKey, setRefreshKey] = useState(0)
  const [finePage, setFinePage] = useState(1)
  const [vehicleError, setVehicleError] = useState(false)
  const refresh = () => setRefreshKey(value => value + 1)


  // Attachment viewer state
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewerAttachments, setViewerAttachments] = useState([])
  const [viewerInitialIndex, setViewerInitialIndex] = useState(0)
  const [viewerInitialShowOcr, setViewerInitialShowOcr] = useState(false)
  
  const [expandedInsurance, setExpandedInsurance] = useState(null)
  const expenseState = useExpenseSummary(id, selectedYear, refreshKey)
  const expenseSummary = expenseState.data
  const detailState = useExpenseRecords(id, { category: activeTab, year: selectedYear, month, page }, refreshKey)
  const fineState = useExpenseRecords(id, { category: 'parking', scope: 'outstanding', page: finePage }, refreshKey, activeTab === 'parking')

  useEffect(() => {
    let active = true
    setLoading(true)
    setVehicleError(false)
    vehicleApi.getById(id)
      .then(response => { if (active) setVehicle(response.data) })
      .catch(() => { if (active) setVehicleError(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id, refreshKey])

  const fuelEntries = activeTab === 'fuel' ? detailState.data?.records || [] : []
  const setFuelEntries = detailState.setRecords
  const serviceEntries = activeTab === 'service' ? detailState.data?.records || [] : []
  const setServiceEntries = detailState.setRecords
  const taxEntries = activeTab === 'tax' ? detailState.data?.records || [] : []
  const setTaxEntries = detailState.setRecords
  const parkingEntries = activeTab === 'parking' ? detailState.data?.records || [] : []
  const setParkingEntries = detailState.setRecords
  const repairEntries = activeTab === 'repair' ? detailState.data?.records || [] : []
  const setRepairEntries = detailState.setRecords
  const insuranceEntries = activeTab === 'insurance' ? detailState.data?.records || [] : []
  const setInsuranceEntries = detailState.setRecords
  const consumableEntries = activeTab === 'consumable' ? detailState.data?.records || [] : []
  const todoEntries = activeTab === 'todo' ? detailState.data?.records || [] : []
  const setTodoEntries = detailState.setRecords
  const reminderEntries = activeTab === 'reminder' ? detailState.data?.records || [] : []
  const setReminderEntries = detailState.setRecords
  const outstandingFines = fineState.data?.records || []
  const setOutstandingFines = fineState.setRecords

  // Deleting the last row can remove a page. Recover to the last valid page.
  useEffect(() => {
    if (detailState.data && page > Math.max(1, detailState.data.pages)) setPage(Math.max(1, detailState.data.pages), true)
  }, [detailState.data, page, setPage])
  useEffect(() => {
    if (fineState.data && finePage > Math.max(1, fineState.data.pages)) setFinePage(Math.max(1, fineState.data.pages))
  }, [fineState.data, finePage])

  const categoryTotals = Object.fromEntries(['fuel', 'service', 'tax', 'parking', 'repair', 'insurance', 'consumable']
    .map(key => [`${key}Total`, expenseSummary?.totals?.[key] ?? 0]))
  const monthlyData = Array.from({ length: 12 }, (_, i) => {
    const row = expenseSummary?.monthly?.find(item => Number(item.month.slice(5)) === i + 1)
    return { month: i + 1, total: row?.total ?? 0, breakdown: row?.breakdown ?? {} }
  })

  // Donut data: full-year or filtered to selectedMonth
  const activeDonutData = useMemo(() => {
    const colorMap = { fuel: '#3b82f6', service: '#22c55e', tax: '#a855f7', parking: '#f59e0b', repair: '#ef4444', insurance: '#10b981', consumable: '#06b6d4' }
    const labelMap = {
      fuel: t('expenses.fuel') || 'Fuel',
      service: t('expenses.service') || 'Service',
      tax: t('expenses.tax') || 'Tax',
      parking: t('expenses.parking') || 'Parking',
      repair: t('expenses.repair') || 'Repairs',
      insurance: t('financial.insurance'),
      consumable: t('financial.consumable'),
    }
    if (selectedMonth !== null) {
      const breakdown = monthlyData[selectedMonth]?.breakdown || {}
      return Object.entries(breakdown)
        .filter(([, v]) => v > 0)
        .map(([key, value]) => ({ label: labelMap[key] || key, value, color: colorMap[key] || '#6b7280' }))
    }
    return [
      { label: labelMap.fuel, value: categoryTotals.fuelTotal, color: colorMap.fuel },
      { label: labelMap.service, value: categoryTotals.serviceTotal, color: colorMap.service },
      { label: labelMap.tax, value: categoryTotals.taxTotal, color: colorMap.tax },
      { label: labelMap.parking, value: categoryTotals.parkingTotal, color: colorMap.parking },
      { label: labelMap.repair, value: categoryTotals.repairTotal, color: colorMap.repair },
      { label: labelMap.insurance, value: categoryTotals.insuranceTotal, color: colorMap.insurance },
      { label: labelMap.consumable, value: categoryTotals.consumableTotal, color: colorMap.consumable },
    ]
  }, [selectedMonth, monthlyData, categoryTotals, t])

  const categories = [
    { label: t('expenses.fuel') || 'Fuel', color: '#3b82f6' },
    { label: t('expenses.service') || 'Service', color: '#22c55e' },
    { label: t('expenses.tax') || 'Tax', color: '#a855f7' },
    { label: t('expenses.parking') || 'Parking', color: '#f59e0b' },
    { label: t('expenses.repair') || 'Repairs', color: '#ef4444' },
    { label: t('financial.insurance'), color: '#10b981' },
    { label: t('financial.consumable'), color: '#06b6d4' },
  ]

  const years = [...new Set([selectedYear, ...(expenseSummary?.available_years || [])])].sort((a, b) => b - a)
  const categoryTotal = month == null ? expenseSummary?.totals?.[activeTab]
    : expenseSummary?.monthly?.find(row => Number(row.month.slice(5)) === month)?.breakdown?.[activeTab] ?? 0


  const recordFor = (type, entryId) => ({ fuel: fuelEntries, service: serviceEntries,
    repair: repairEntries, tax: taxEntries, parking: parkingEntries,
    insurance: insuranceEntries, consumable: consumableEntries, reminder: reminderEntries, todo: todoEntries })[type]?.find(e => e.id === entryId)

  const handleCancelRecurring = async (type, entryId) => {
    const msg = type === 'insurance'
      ? (t('recurring.cancelInsuranceConfirm')
         || 'Cancel this insurance policy? This will stop future recurring costs and set the end date to today.')
      : (t('recurring.stopRepeatingConfirm')
         || 'Stop this recurring series? Future entries will no longer be auto-generated.')
    if (!confirm(msg)) return
    try {
      if (type === 'insurance') {
        const res = await insuranceApi.cancel(entryId, mutationOptions(recordFor(type, entryId)))
        setInsuranceEntries(prev => prev.map(e => e.id === entryId ? res.data.policy : e))
      } else if (type === 'tax') {
        const res = await taxApi.cancel(entryId, mutationOptions(recordFor(type, entryId)))
        setTaxEntries(prev => prev.map(e => e.id === entryId ? res.data.entry : e))
      } else if (type === 'parking') {
        // F34 — stop a recurring permit/subscription series.
        const res = await parkingApi.cancel(entryId, mutationOptions(recordFor(type, entryId)))
        setParkingEntries(prev => prev.map(e => e.id === entryId ? res.data.entry : e))
      }
      refresh()
    } catch (error) {
      console.error('Failed to cancel recurring:', error)
      toast.error(error.response?.data?.error
        || t('recurring.cancelFailed')
        || 'Could not stop this recurring series. Please try again.')
    }
  }

  const handleDelete = async (type, entryId) => {
    if (!confirm(t('common.confirmDelete') || 'Are you sure you want to delete this entry?')) return
    
    try {
      switch (type) {
        case 'consumable':
          await consumableApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          break
        case 'fuel':
          await fuelApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setFuelEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'service':
          await serviceApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setServiceEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'repair':
          await repairApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setRepairEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'tax':
          await taxApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setTaxEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'parking':
          await api.delete(`/parking/${entryId}`, mutationOptions(recordFor(type, entryId)))
          setParkingEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'reminder':
          await reminderApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setReminderEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'todo':
          await api.delete(`/todos/${entryId}`, mutationOptions(recordFor(type, entryId)))
          setTodoEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'insurance':
          await insuranceApi.delete(entryId, mutationOptions(recordFor(type, entryId)))
          setInsuranceEntries(prev => prev.filter(e => e.id !== entryId))
          break
      }
      refresh()
    } catch (error) {
      console.error('Failed to delete:', error)
      toast.error(error.response?.data?.error
        || t('common.deleteFailed')
        || 'Could not delete this entry. Please try again.')
    }
  }

  // Navigate to edit page for entry
  const handleEdit = (type, entryId) => {
    const editRoutes = {
      consumable: `/vehicles/${id}/consumable/add?edit=${entryId}`,
      fuel: `/vehicles/${id}/fuel/add?edit=${entryId}`,
      service: `/vehicles/${id}/service/add?edit=${entryId}`,
      repair: `/vehicles/${id}/repair/add?edit=${entryId}`,
      tax: `/vehicles/${id}/tax/add?edit=${entryId}`,
      parking: `/vehicles/${id}/parking/add?edit=${entryId}`,
      reminder: `/vehicles/${id}/reminder/add?edit=${entryId}`,
      todo: `/vehicles/${id}/todo/add?edit=${entryId}`,
      insurance: `/vehicles/${id}/insurance/add?edit=${entryId}`,
    }
    navigate(editRoutes[type], { state: { expenseReturnTo: location.pathname + location.search } })
  }

  const handleMonthClick = (monthIndex) => {
    setSelectedMonth(selectedMonth === monthIndex ? null : monthIndex)
  }

  // F14 — settle an outstanding parking fine (optimistic, offline-tolerant).
  const handleMarkFinePaid = async (fine) => {
    const previous = outstandingFines
    const previousParking = parkingEntries
    setOutstandingFines(prev => prev.filter(f => f.id !== fine.id))
    setParkingEntries(prev => prev.map(e =>
      e.id === fine.id ? { ...e, fine_status: 'paid' } : e
    ))
    try {
      const response = await parkingApi.update(fine.id, { fine_status: 'paid' }, mutationOptions(fine))
      setParkingEntries(prev => prev.map(e => e.id === fine.id ? response.data.entry : e))
      refresh()
      toast.success(t('parking.markedPaid') || 'Fine marked as paid')
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        return
      }
      setOutstandingFines(previous)
      setParkingEntries(previousParking)
      toast.error(t('parking.markPaidError') || 'Could not update fine — try again')
    }
  }

  // F47 — settle a pending tax (optimistic, offline-tolerant). Sets status
  // 'paid' + paid_date today so it drops out of the Coming-up feed.
  const handleMarkTaxPaid = async (entry) => {
    const previous = taxEntries
    const today = localDate()
    setTaxEntries(prev => prev.map(e =>
      e.id === entry.id ? { ...e, status: 'paid', paid_date: today } : e
    ))
    try {
      const response = await taxApi.update(entry.id, { status: 'paid', paid_date: today }, mutationOptions(entry))
      setTaxEntries(prev => prev.map(e => e.id === entry.id ? response.data.entry : e))
      refresh()
      toast.success(t('taxes.markedPaid') || 'Tax marked as paid')
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        return
      }
      setTaxEntries(previous)
      toast.error(t('taxes.markPaidError') || 'Could not update tax — try again')
    }
  }

  // F55 — copy a policy number to the clipboard from the insurance contact card.
  const copyPolicyNumber = async (value) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      toast.success(t('reportShare.copied') || 'Copied')
    } catch {
      toast.error(t('reportShare.copyFailed') || 'Could not copy')
    }
  }

  // Open attachment viewer
  const openAttachmentViewer = (attachments, index = 0, showOcr = false) => {
    if (attachments && attachments.length > 0) {
      setViewerAttachments(attachments)
      setViewerInitialIndex(index)
      setViewerInitialShowOcr(showOcr)
      setViewerOpen(true)
    }
  }

  // Render attachment button for entries
  const renderAttachmentButton = (entry) => {
    const attachments = entry.attachments || []
    if (attachments.length === 0) return <span className="text-(--color-text-muted)">-</span>
    
    const ocrIndex = attachments.findIndex(a => a.ocr_processed && a.has_text)
    const hasOcrText = ocrIndex !== -1
    
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={() => openAttachmentViewer(attachments)}
          className="flex items-center gap-1 text-yellow-500 hover:text-yellow-400 transition-colors"
          title={`${attachments.length} ${t('common.attachment') || 'attachment'}${attachments.length > 1 ? 's' : ''}`}
        >
          {Icons.eye}
          <span className="text-xs">({attachments.length})</span>
        </button>
        {hasOcrText && (
          <button
            onClick={(e) => { e.stopPropagation(); openAttachmentViewer(attachments, ocrIndex, true) }}
            className="flex items-center gap-0.5 px-1 py-0.5 rounded-sm text-purple-400 hover:text-purple-300 hover:bg-purple-500/10 transition-colors"
            title={t('attachments.ocrBadgeTitle') || 'Has scanned text — tap to view'}
          >
            {Icons.scan}
          </button>
        )}
      </div>
    )
  }

  // Tab definitions
  const tabs = [
    { id: 'consumable', label: t('financial.consumable'), icon: Icons.service, count: activeTab === 'consumable' ? detailState.data?.total : undefined },
    { id: 'fuel', label: t('expenses.fuel') || 'Fuel', icon: Icons.fuel, count: activeTab === 'fuel' ? detailState.data?.total : undefined },
    { id: 'service', label: t('expenses.service') || 'Service', icon: Icons.service, count: activeTab === 'service' ? detailState.data?.total : undefined },
    { id: 'tax', label: t('expenses.tax') || 'Tax', icon: Icons.tax, count: activeTab === 'tax' ? detailState.data?.total : undefined },
    { id: 'parking', label: t('expenses.parking') || 'Parking', icon: Icons.parking, count: activeTab === 'parking' ? detailState.data?.total : undefined },
    { id: 'repair', label: t('expenses.repair') || 'Repairs', icon: Icons.repair, count: activeTab === 'repair' ? detailState.data?.total : undefined },
    { id: 'insurance', label: t('expenses.insurance') || 'Insurance', icon: Icons.shield, count: activeTab === 'insurance' ? detailState.data?.total : undefined },
    { id: 'todo', label: t('expenses.todos') || 'Todos', icon: Icons.todo, count: activeTab === 'todo' ? detailState.data?.total : undefined },
    { id: 'reminder', label: t('expenses.reminders') || 'Reminders', icon: Icons.reminder, count: activeTab === 'reminder' ? detailState.data?.total : undefined },
  ]

  // Render table based on active tab
  const renderTable = () => {
    switch (activeTab) {
      case 'consumable':
        return <table className="w-full"><thead><tr className="text-left text-sm">
          <th className="p-3">{t('common.date')}</th><th className="p-3">{t('addService.description')}</th>
          <th className="p-3">{t('addFuel.totalCost')}</th><th className="p-3">{t('common.attachment')}</th><th className="p-3">{t('common.actions')}</th>
        </tr></thead><tbody>{consumableEntries.map(entry => <tr key={entry.id} className="border-t border-(--color-border)">
          <td className="p-3">{formatDate(entry.date)}</td><td className="p-3">{entry.title || entry.description || entry.consumable_type}</td>
          <td className="p-3">{formatCurrency(entry.amount, entry.currency)}</td><td className="p-3">{renderAttachmentButton(entry)}</td>
          <td className="p-3"><button title={t('common.edit')} onClick={() => handleEdit('consumable', entry.id)}>{Icons.edit}</button>
            <button title={t('common.delete')} onClick={() => handleDelete('consumable', entry.id)}>{Icons.delete}</button></td>
        </tr>)}</tbody></table>
      case 'fuel':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addFuel.odometer') || 'Odometer'}</th>
                <th className="pb-3 px-4">{volumeUnitLabel(user, t)}</th>
                <th className="pb-3 px-4">{t('addFuel.pricePerUnit', { unit: volumeUnitLabel(user, t) })}</th>
                <th className="pb-3 px-4">{t('addFuel.totalCost') || 'Total Price'}</th>
                <th className="pb-3 px-4">{t('addFuel.fuelType') || 'Fuel Type'}</th>
                <th className="pb-3 px-4">{t('addFuel.station') || 'Station'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {fuelEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">
                    {entry.liters != null ? litersToDisplayVolume(entry.liters, user).toFixed(2) : '--'} {volumeUnitLabel(user, t)}
                  </td>
                  <td className="py-3 px-4 text-(--color-accent)">
                    {formatCurrency(entry.price_per_liter != null ? pricePerLiterToDisplay(entry.price_per_liter, user) : entry.price_per_liter, entry.currency)}
                  </td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.total_price, entry.currency)}</td>
                  <td className="py-3 px-4">{entry.fuel_type || '-'}</td>
                  <td className="py-3 px-4">{entry.station || '-'}</td>
                  <td className="py-3 px-4">
                    {renderAttachmentButton(entry)}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('fuel', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      <button 
                        onClick={() => handleDelete('fuel', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {fuelEntries.length === 0 && (
                <tr><td colSpan={9} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'service':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addService.serviceType') || 'Service Type'}</th>
                <th className="pb-3 px-4">{t('addFuel.odometer') || 'Odometer'}</th>
                <th className="pb-3 px-4">{t('addService.partsCost') || 'Parts Cost'}</th>
                <th className="pb-3 px-4">{t('addService.laborCost') || 'Labor Cost'}</th>
                <th className="pb-3 px-4">{t('addService.totalCost') || 'Total Cost'}</th>
                <th className="pb-3 px-4">{t('addService.provider') || 'Provider'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {serviceEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{(entry.service_types?.length > 0 ? entry.service_types.map(st => st.replace(/_/g, ' ')).join(', ') : entry.service_type || entry.title || '-')}</td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.parts_cost || 0, entry.currency)}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.labor_cost || 0, entry.currency)}</td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.amount, entry.currency)}</td>
                  <td className="py-3 px-4">
                    <div title={entry.work_order_number ? `${t('addService.workOrder') || 'Work order #'}: ${entry.work_order_number}` : undefined}>
                      <span>{entry.provider || '-'}</span>
                      {entry.work_order_number && (
                        <span className="block text-xs text-(--color-text-muted)">
                          #{entry.work_order_number}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleEdit('service', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      <button 
                        onClick={() => handleDelete('service', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {serviceEntries.length === 0 && (
                <tr><td colSpan={9} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'tax':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addTax.taxType') || 'Tax Type'}</th>
                <th className="pb-3 px-4">{t('addTax.amount') || 'Amount'}</th>
                <th className="pb-3 px-4">{t('addTax.dueDate') || 'Due Date'}</th>
                <th className="pb-3 px-4">{t('addTax.linkedInsurance') || 'Insurance'}</th>
                <th className="pb-3 px-4">{t('addTax.recurring') || 'Recurring'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {taxEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center gap-2">
                      {entry.tax_type || entry.title || '-'}
                      {entry.status === 'pending' && (
                        <span className="inline-flex items-center px-2 py-0.5 bg-amber-500/15 text-amber-600 dark:text-amber-400 rounded-full text-xs font-medium">
                          {t('taxes.unpaid') || 'Unpaid'}
                        </span>
                      )}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.amount, entry.currency)}</td>
                  <td className="py-3 px-4">{formatDate(entry.due_date)}</td>
                  <td className="py-3 px-4">
                    {entry.insurance_policy ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-full text-xs">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                        {entry.insurance_policy.provider}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="py-3 px-4">{entry.recurring ? <RecurringChip entry={entry} t={t} /> : '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      {entry.status === 'pending' && (
                        <button
                          onClick={() => handleMarkTaxPaid(entry)}
                          className="px-2 py-1 rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25 text-xs font-medium whitespace-nowrap transition-colors"
                        >
                          {t('taxes.markPaid') || 'Mark paid'}
                        </button>
                      )}
                      <button
                        onClick={() => handleEdit('tax', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      {entry.recurring && (
                        <button
                          onClick={() => handleCancelRecurring('tax', entry.id)}
                          className="text-orange-500 hover:text-orange-400 p-1"
                          title={t('recurring.stopRepeating') || 'Stop repeating'}
                        >
                          {Icons.cancelRecurring}
                        </button>
                      )}
                      <button 
                        onClick={() => handleDelete('tax', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {taxEntries.length === 0 && (
                <tr><td colSpan={8} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'parking':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addParking.location') || 'Location'}</th>
                <th className="pb-3 px-4">{t('addParking.parkingType') || 'Type'}</th>
                <th className="pb-3 px-4">{t('addParking.amount') || 'Amount'}</th>
                <th className="pb-3 px-4">{t('addParking.duration') || 'Duration'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {parkingEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.location || '-'}</td>
                  <td className="py-3 px-4">
                    {entry.parking_type || '-'}
                    {entry.recurring && (
                      <div className="mt-1"><RecurringChip entry={entry} t={t} /></div>
                    )}
                  </td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.amount, entry.currency)}</td>
                  <td className="py-3 px-4">{entry.duration || '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleEdit('parking', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      {entry.recurring && (
                        <button
                          onClick={() => handleCancelRecurring('parking', entry.id)}
                          className="text-orange-500 hover:text-orange-400 p-1"
                          title={t('recurring.stopRepeating') || 'Stop repeating'}
                        >
                          {Icons.cancelRecurring}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete('parking', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {parkingEntries.length === 0 && (
                <tr><td colSpan={7} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'repair':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addRepair.repairType') || 'Repair Type'}</th>
                <th className="pb-3 px-4">{t('addFuel.odometer') || 'Odometer'}</th>
                <th className="pb-3 px-4">{t('addRepair.partsCost') || 'Parts Cost'}</th>
                <th className="pb-3 px-4">{t('addRepair.laborCost') || 'Labor Cost'}</th>
                <th className="pb-3 px-4">{t('addRepair.totalCost') || 'Total Cost'}</th>
                <th className="pb-3 px-4">{t('addRepair.provider') || 'Provider'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {repairEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">
                    <div title={entry.root_cause ? `${t('addRepair.rootCause') || 'Root cause'}: ${entry.root_cause}` : undefined}>
                      <span>{entry.repair_type || entry.title || '-'}</span>
                      {entry.root_cause && (
                        <span className="block text-xs text-(--color-text-muted) max-w-xs truncate">
                          {entry.root_cause}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.parts_cost || 0, entry.currency)}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.labor_cost || 0, entry.currency)}</td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.amount, entry.currency)}</td>
                  <td className="py-3 px-4">{entry.provider || '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('repair', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      <button 
                        onClick={() => handleDelete('repair', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {repairEntries.length === 0 && (
                <tr><td colSpan={9} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'insurance':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('addInsurance.provider') || 'Provider'}</th>
                <th className="pb-3 px-4">{t('addInsurance.policyNumber') || 'Policy #'}</th>
                <th className="pb-3 px-4">{t('addInsurance.policyType') || 'Type'}</th>
                <th className="pb-3 px-4">{t('addInsurance.premium') || 'Premium'}</th>
                <th className="pb-3 px-4">{t('addInsurance.paymentFrequency') || 'Frequency'}</th>
                <th className="pb-3 px-4">{t('addInsurance.startDate') || 'Start Date'}</th>
                <th className="pb-3 px-4">{t('addInsurance.endDate') || 'End Date'}</th>
                <th className="pb-3 px-4">{t('addInsurance.status') || 'Status'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {insuranceEntries.map(entry => {
                const isOpen = expandedInsurance === entry.id
                const hasContact = entry.claims_phone || entry.agent_phone || entry.agent_email ||
                  entry.agent_name || entry.policy_number || entry.coverage_amount != null || entry.deductible != null
                return (
                <Fragment key={entry.id}>
                <tr className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4 font-medium">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setExpandedInsurance(isOpen ? null : entry.id)}
                        className="text-(--color-text-muted) hover:text-(--color-accent) p-0.5 shrink-0 transition-transform"
                        style={{ transform: isOpen ? 'rotate(180deg)' : 'none' }}
                        aria-expanded={isOpen}
                        aria-label={t('insurance.contactDetails') || 'Contact details'}
                        title={t('insurance.contactDetails') || 'Contact details'}
                      >
                        {Icons.chevronDown}
                      </button>
                      <span>{entry.provider}</span>
                    </div>
                    {entry.renewed_from_id && (
                      <span className="mt-1 block text-2xs font-normal text-amber-600 dark:text-amber-400">
                        {t('insurance.autoRenewed') || 'Auto-renewed'} · {t('insurance.confirmPremium') || 'confirm premium'}
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4">{entry.policy_number || '-'}</td>
                  <td className="py-3 px-4 capitalize">{entry.policy_type?.replace('_', ' ') || '-'}</td>
                  <td className="py-3 px-4 text-(--color-accent) font-medium">{formatCurrency(entry.premium, entry.currency)}<span className="block text-xs">{t('expensePages.policyEstimate')}: {entry.period_amount == null ? t('financial.unavailable') : formatCurrency(entry.period_amount, detailState.data?.display_currency)}</span></td>
                  <td className="py-3 px-4 capitalize">{entry.payment_frequency || '-'}</td>
                  <td className="py-3 px-4">{formatDate(entry.start_date)}</td>
                  <td className="py-3 px-4">{formatDate(entry.end_date)}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      entry.status === 'active' ? 'bg-green-500/20 text-green-400' :
                      entry.status === 'expired' ? 'bg-red-500/20 text-red-400' :
                      'bg-gray-500/20 text-(--color-text-secondary)'
                    }`}>
                      {entry.status || 'active'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    {renderAttachmentButton(entry)}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('insurance', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      {entry.status === 'active' && (
                        <button
                          onClick={() => handleCancelRecurring('insurance', entry.id)}
                          className="text-orange-500 hover:text-orange-400 p-1"
                          title={t('recurring.cancelInsurance') || 'Cancel insurance (stop recurring costs)'}
                        >
                          {Icons.cancelRecurring}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete('insurance', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-(--color-border) bg-(--color-bg-tertiary)/40">
                    <td colSpan={10} className="px-4 py-4">
                      {hasContact ? (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
                          {/* Policy number + copy */}
                          {entry.policy_number && (
                            <div>
                              <p className="text-2xs uppercase tracking-wide text-(--color-text-muted) mb-0.5">{t('addInsurance.policyNumber') || 'Policy #'}</p>
                              <div className="flex items-center gap-2">
                                <span className="font-mono break-all">{entry.policy_number}</span>
                                <button
                                  onClick={() => copyPolicyNumber(entry.policy_number)}
                                  className="text-(--color-text-muted) hover:text-(--color-accent) shrink-0"
                                  aria-label={t('insurance.copyPolicyNumber') || 'Copy policy number'}
                                  title={t('insurance.copyPolicyNumber') || 'Copy policy number'}
                                >
                                  {Icons.copy}
                                </button>
                              </div>
                            </div>
                          )}
                          {/* Claims line */}
                          {entry.claims_phone && (
                            <div>
                              <p className="text-2xs uppercase tracking-wide text-(--color-text-muted) mb-0.5">{t('insurance.claimsPhone') || 'Claims line'}</p>
                              <a href={`tel:${entry.claims_phone}`} className="inline-flex items-center gap-1.5 text-(--color-accent) hover:underline">
                                <span className="shrink-0">{Icons.phone}</span>{entry.claims_phone}
                              </a>
                            </div>
                          )}
                          {/* Agent */}
                          {(entry.agent_name || entry.agent_phone || entry.agent_email) && (
                            <div>
                              <p className="text-2xs uppercase tracking-wide text-(--color-text-muted) mb-0.5">{t('insurance.agent') || 'Agent'}</p>
                              {entry.agent_name && <p className="text-(--color-text-secondary)">{entry.agent_name}</p>}
                              {entry.agent_phone && (
                                <a href={`tel:${entry.agent_phone}`} className="inline-flex items-center gap-1.5 text-(--color-accent) hover:underline">
                                  <span className="shrink-0">{Icons.phone}</span>{entry.agent_phone}
                                </a>
                              )}
                              {entry.agent_email && (
                                <a href={`mailto:${entry.agent_email}`} className="mt-0.5 flex items-center gap-1.5 text-(--color-accent) hover:underline break-all">
                                  <span className="shrink-0">{Icons.mail}</span>{entry.agent_email}
                                </a>
                              )}
                            </div>
                          )}
                          {/* Coverage / deductible */}
                          {entry.coverage_amount != null && (
                            <div>
                              <p className="text-2xs uppercase tracking-wide text-(--color-text-muted) mb-0.5">{t('addInsurance.coverageAmount') || 'Coverage'}</p>
                              <span>{formatCurrency(entry.coverage_amount, entry.currency)}</span>
                            </div>
                          )}
                          {entry.deductible != null && (
                            <div>
                              <p className="text-2xs uppercase tracking-wide text-(--color-text-muted) mb-0.5">{t('addInsurance.deductible') || 'Deductible'}</p>
                              <span>{formatCurrency(entry.deductible, entry.currency)}</span>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-(--color-text-muted)">{t('insurance.noContactDetails') || 'No contact details saved for this policy.'}</p>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
                )
              })}
              {insuranceEntries.length === 0 && (
                <tr><td colSpan={10} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'todo':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.title') || 'Title'}</th>
                <th className="pb-3 px-4">{t('addTodo.description') || 'Description'}</th>
                <th className="pb-3 px-4">{t('addTodo.priority') || 'Priority'}</th>
                <th className="pb-3 px-4">{t('addTodo.dueDate') || 'Due Date'}</th>
                <th className="pb-3 px-4">{t('addTodo.status') || 'Status'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {todoEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{entry.title}</td>
                  <td className="py-3 px-4 max-w-xs truncate">{entry.description || '-'}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      entry.priority === 'high' ? 'bg-red-500/20 text-red-400' :
                      entry.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-green-500/20 text-green-400'
                    }`}>
                      {entry.priority || 'low'}
                    </span>
                  </td>
                  <td className="py-3 px-4">{formatDate(entry.due_date)}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      entry.completed ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-(--color-text-secondary)'
                    }`}>
                      {entry.completed ? t('common.completed') || 'Completed' : t('common.pending') || 'Pending'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('todo', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      <button 
                        onClick={() => handleDelete('todo', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {todoEntries.length === 0 && (
                <tr><td colSpan={6} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'reminder':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-(--color-text-secondary) text-sm border-b border-(--color-border)">
                <th className="pb-3 px-4">{t('common.title') || 'Title'}</th>
                <th className="pb-3 px-4">{t('addReminder.reminderType') || 'Type'}</th>
                <th className="pb-3 px-4">{t('addReminder.dueDate') || 'Due Date'}</th>
                <th className="pb-3 px-4">{t('addReminder.dueMileage') || 'Due Mileage'}</th>
                <th className="pb-3 px-4">{t('addReminder.status') || 'Status'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {reminderEntries.map(entry => (
                <tr key={entry.id} className="border-b border-(--color-border) hover:bg-(--color-bg-tertiary)">
                  <td className="py-3 px-4">{entry.title}</td>
                  <td className="py-3 px-4">{entry.reminder_type || '-'}</td>
                  <td className="py-3 px-4">{formatDate(entry.due_date)}</td>
                  <td className="py-3 px-4">{entry.due_mileage?.toLocaleString() || '-'} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      entry.status === 'completed' ? 'bg-green-500/20 text-green-400' :
                      entry.status === 'overdue' ? 'bg-red-500/20 text-red-400' :
                      'bg-yellow-500/20 text-yellow-400'
                    }`}>
                      {entry.status || 'pending'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('reminder', entry.id)}
                        className="text-(--color-accent) hover:text-(--color-accent) p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      <button 
                        onClick={() => handleDelete('reminder', entry.id)}
                        className="text-red-500 hover:text-red-400 p-1"
                        title={t('common.delete') || 'Delete'}
                      >
                        {Icons.delete}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {reminderEntries.length === 0 && (
                <tr><td colSpan={6} className="py-8 text-center text-(--color-text-muted)">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      default:
        return null
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-(--color-bg-primary) pb-20">
        {/* Header placeholder */}
        <div className="sticky top-0 z-10 bg-(--color-bg-primary) border-b border-(--color-border) p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-40 rounded-sm" />
              <Skeleton className="h-3 w-24 rounded-sm" />
            </div>
          </div>
        </div>
        <SkeletonScreen className="p-4 space-y-4">
          {/* Tab bar placeholder */}
          <div className="flex gap-2 overflow-hidden">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-20 rounded-full shrink-0" />
            ))}
          </div>
          {/* Summary card placeholder */}
          <Skeleton className="h-24 w-full rounded-2xl" />
          {/* Row placeholders */}
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-4 flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-full shrink-0" />
              <div className="flex-1 space-y-2 min-w-0">
                <Skeleton className="h-3.5 w-1/2 rounded-sm" />
                <Skeleton className="h-3 w-1/4 rounded-sm" />
              </div>
              <Skeleton className="h-4 w-14 rounded-sm shrink-0" />
            </div>
          ))}
        </SkeletonScreen>
      </div>
    )
  }

  if (vehicleError) return <div role="alert" className="p-4">{t('expensePages.loadFailed')} <button onClick={refresh}>{t('expensePages.retry')}</button></div>

  return (
    <div className="min-h-screen bg-(--color-bg-primary) text-(--color-text-primary) pb-20">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-(--color-bg-primary) border-b border-(--color-border)">
        <div className="flex items-center gap-3 p-4">
          <button 
            type="button"
            aria-label={t('expenses.backToVehicle')}
            onClick={() => navigate(`/vehicles/${id}`)}
            className="p-2 -ml-2 min-w-11 min-h-11 rounded-lg hover:bg-(--color-bg-tertiary) transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-text-primary)"
          >
            {Icons.arrowBack}
          </button>
          <div>
            <h1 className="text-lg font-semibold">{t('expenses.expensesManager') || 'Expenses Manager'}</h1>
            <p className="text-xs text-(--color-text-secondary)">
              {vehicle?.make} {vehicle?.model}
            </p>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-6">
      <FinancialBasis data={expenseSummary} error={expenseState.error} />
      {expenseState.error && <button className="btn btn-secondary" onClick={refresh}>{t('expensePages.retry')}</button>}
      {/* Top Section - Charts */}
      {expenseSummary && (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Donut Chart Card */}
        <div className="bg-(--color-bg-secondary) rounded-xl p-6 border border-(--color-border)">
          {selectedMonth !== null && (
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium px-2 py-1 rounded-full bg-(--color-bg-tertiary) text-(--color-text-primary)">
                {monthNames[selectedMonth]} {selectedYear}
              </span>
            </div>
          )}
          <DonutChart
            data={activeDonutData}
            currency={expenseSummary.display_currency}
            centerText={selectedMonth !== null ? monthNamesShort[selectedMonth] : `${vehicle?.year || ''} ${vehicle?.make || ''}`}
            centerSubtext={selectedMonth !== null ? String(selectedYear) : (vehicle?.model || '')}
          />
        </div>

        {/* Bar Chart Card */}
        <div className="bg-(--color-bg-secondary) rounded-xl p-6 border border-(--color-border)">
          <div className="flex items-center justify-between mb-4">
            <span className="text-(--color-text-secondary) text-sm">{t('expenses.selectYear') || 'Select Year'}</span>
            <select
              aria-label={t('expenses.selectYear')}
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="bg-(--color-bg-tertiary) border border-(--color-border) rounded-sm px-3 py-1 text-(--color-text-primary)"
            >
              {years.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
          <BarChart
            data={monthlyData}
            categories={categories}
            currency={expenseSummary.display_currency}
            year={selectedYear}
            title={t('charts.monthlyExpenses') || 'Monthly Expenses'}
            onMonthClick={handleMonthClick}
            selectedMonth={selectedMonth}
            hintText={t('expenses.clickMonthHint') || 'Tap a month to filter'}
          />
        </div>
      </div>

      )}

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 mb-6 overflow-x-auto pb-2">
        {tabs.map(tab => (
          <TabButton
            key={tab.id}
            tabId={tab.id}
            active={activeTab === tab.id}
            icon={tab.icon}
            label={tab.label}
            count={tab.count}
            onClick={() => setActiveTab(tab.id)}
          />
        ))}
      </div>

      {/* F14 — Unpaid fines for this vehicle */}
      {activeTab === 'parking' && fineState.loading && <p role="status">{t('common.loading')}</p>}
      {activeTab === 'parking' && fineState.error && <p role="alert">{t('expensePages.finesFailed')} <button onClick={refresh}>{t('expensePages.retry')}</button></p>}
      {activeTab === 'parking' && fineState.data && outstandingFines.length > 0 && (
        <div className="bg-orange-500/5 border border-orange-500/20 rounded-xl p-4 mb-6">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold text-orange-600 dark:text-orange-400">
              {t('parking.unpaidFines') || 'Unpaid fines'} ({fineState.data.total})
            </h3>
            <span className="text-sm font-semibold">
              {t('expensePages.pageTotal')}:{' '}
              {formatCurrency(fineState.data.page_total, fineState.data.display_currency)}
            </span>
          </div>
          <ul className="space-y-2">
            {outstandingFines.map(fine => (
              <li
                key={fine.id}
                className="flex items-center gap-3 bg-(--color-bg-secondary) border border-(--color-border) rounded-lg px-3 py-2"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {fine.fine_reason || fine.location || (t('due.kind.fine') || 'Parking fine')}
                  </p>
                  <p className="text-xs text-(--color-text-muted)">
                    {formatDate(fine.date)}
                    {fine.fine_status === 'contested' ? ` • ${t('parking.contested') || 'Contested'}` : ''}
                  </p>
                </div>
                <span className="text-sm font-semibold text-orange-500 whitespace-nowrap">
                  {formatCurrency(fine.amount, fine.currency)}
                </span>
                <button
                  onClick={() => handleMarkFinePaid(fine)}
                  className="btn btn-secondary btn-sm whitespace-nowrap"
                >
                  {t('parking.markPaid') || 'Mark paid'}
                </button>
              </li>
            ))}
          </ul>
          {fineState.data.converted === false && <p>{t('financial.partial')}</p>}
          <ExpensePagination data={fineState.data} page={finePage} onPage={setFinePage} />
        </div>
      )}

      {/* Data Table */}
      {detailState.loading ? <p role="status">{t('common.loading')}</p>
        : detailState.error ? <p role="alert">{t('expensePages.loadFailed')} <button onClick={refresh}>{t('expensePages.retry')}</button></p>
        : detailState.data && <>
          <p className="text-xs mb-2">{t(['todo', 'reminder'].includes(activeTab) ? 'expensePages.tasksAllDates' : activeTab === 'insurance' ? 'expensePages.policyRows' : 'expensePages.recordRows')}</p>
          {detailState.data.records.length ? <div className="bg-(--color-bg-secondary) rounded-xl border border-(--color-border) overflow-x-auto">{renderTable()}</div>
            : <p>{t('expenses.noEntries')}</p>}
          {!['todo', 'reminder'].includes(activeTab) && <div className="text-sm py-2">
            <p>{t('expensePages.pageTotal')}: {formatCurrency(detailState.data.page_total, detailState.data.display_currency)}</p>
            {detailState.data.converted === false && <p>{t('financial.partial')}</p>}
            {expenseSummary && <p>{t('expensePages.periodTotal')}: {formatCurrency(categoryTotal ?? 0, expenseSummary.display_currency)}</p>}
          </div>}
          <ExpensePagination data={detailState.data} page={page} onPage={setPage} />
        </>}

      </div>

      {/* Attachment Viewer Modal */}
      <AttachmentViewer
        attachments={viewerAttachments}
        initialIndex={viewerInitialIndex}
        initialShowOcr={viewerInitialShowOcr}
        isOpen={viewerOpen}
        onClose={() => setViewerOpen(false)}
      />
    </div>
  )
}
