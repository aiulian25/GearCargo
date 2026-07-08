import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'

// SVG Icons
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
  wrench: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  tools: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h4L17.5 10.5a2.121 2.121 0 0 0-3-3L4 18v3z"/><path d="M14.5 5.5l4 4"/>
      <path d="M12 8L7 3 3 7l5 5"/>
    </svg>
  ),
  receipt: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/>
      <path d="M16 8H8M16 12H8M10 16H8"/>
    </svg>
  ),
  parking: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/>
    </svg>
  ),
  calendar: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
}

// Simple bar chart component
const BarChart = ({ data, maxValue, color, label }) => {
  return (
    <div className="space-y-2">
      {data.map((item, idx) => (
        <div key={idx} className="flex items-center gap-3">
          <span className="text-xs text-[var(--color-text-secondary)] w-12 text-right shrink-0">
            {item.label}
          </span>
          <div className="flex-1 h-6 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
            <div 
              className={`h-full ${color} rounded-full transition-all duration-500`}
              style={{ width: `${maxValue > 0 ? (item.value / maxValue) * 100 : 0}%` }}
            />
          </div>
          <span className="text-xs font-medium w-16 text-right shrink-0">
            {item.displayValue}
          </span>
        </div>
      ))}
    </div>
  )
}

// Donut chart component
const DonutChart = ({ data, total, centerLabel, totalLabel = 'Total' }) => {
  const radius = 60
  const strokeWidth = 20
  const circumference = 2 * Math.PI * radius
  
  let currentOffset = 0
  const segments = data.map((item, idx) => {
    const percentage = total > 0 ? item.value / total : 0
    const dashLength = percentage * circumference
    const dashOffset = -currentOffset
    currentOffset += dashLength
    return { ...item, dashLength, dashOffset, percentage }
  })
  
  return (
    <div className="relative flex items-center justify-center">
      <svg width="160" height="160" viewBox="0 0 160 160">
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke="var(--color-bg-tertiary)"
          strokeWidth={strokeWidth}
        />
        {segments.map((segment, idx) => (
          <circle
            key={idx}
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke={segment.color}
            strokeWidth={strokeWidth}
            strokeDasharray={`${segment.dashLength} ${circumference}`}
            strokeDashoffset={segment.dashOffset}
            transform="rotate(-90 80 80)"
            className="transition-all duration-500"
          />
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold">{centerLabel}</span>
        <span className="text-xs text-[var(--color-text-secondary)]">{totalLabel}</span>
      </div>
    </div>
  )
}

// Lightweight responsive SVG line chart (no chart library).
// points: [{ label, value(number|null) }]. Null values break the line so months
// without data (e.g. no odometer reading) are not drawn as zero.
const LineChart = ({ points, formatValue, ariaLabel, color = 'var(--color-accent)' }) => {
  // viewBox keeps a fixed aspect ratio (NO preserveAspectRatio:none — that
  // stretched the chart to full width AND height). The 2-column grid + page
  // max-width now bound the width, so it renders compact and proportional.
  const W = 340, H = 148, PL = 12, PR = 12, PT = 20, PB = 12
  const gid = useMemo(() => 'gc-line-' + Math.random().toString(36).slice(2, 9), [])
  const n = points.length
  const valid = points.map(p => p.value).filter(v => v != null)
  if (valid.length < 2) return null
  const min = Math.min(...valid)
  const max = Math.max(...valid)
  const range = (max - min) || 1
  const xAt = (i) => PL + (n === 1 ? 0 : (i / (n - 1)) * (W - PL - PR))
  const yAt = (v) => (H - PB) - ((v - min) / range) * (H - PT - PB)

  // Continuous segments, breaking where value is null so gaps aren't drawn as 0.
  const segments = []
  let cur = []
  points.forEach((p, i) => {
    if (p.value == null) { if (cur.length) { segments.push(cur); cur = [] } }
    else cur.push([xAt(i), yAt(p.value)])
  })
  if (cur.length) segments.push(cur)

  const areaPath = (seg) =>
    `M ${seg.map(p => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L ')} ` +
    `L ${seg[seg.length - 1][0].toFixed(1)} ${(H - PB).toFixed(1)} ` +
    `L ${seg[0][0].toFixed(1)} ${(H - PB).toFixed(1)} Z`

  // Emphasize the most recent (last non-null) point and label it directly.
  let lastIdx = -1
  for (let i = n - 1; i >= 0; i--) { if (points[i].value != null) { lastIdx = i; break } }
  const gridYs = [0, 1, 2, 3].map(g => PT + g * ((H - PT - PB) / 3))
  const labelIdx = new Set([0, Math.floor((n - 1) / 2), n - 1])

  return (
    <svg viewBox={`0 0 ${W} ${H + 14}`} className="w-full h-auto" role="img" aria-label={ariaLabel}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridYs.map((y, i) => (
        <line key={`g${i}`} x1={PL} x2={W - PR} y1={y} y2={y}
          stroke="var(--color-border)" strokeOpacity="0.6" strokeWidth="1" />
      ))}
      {segments.map((seg, si) => (
        <path key={`a${si}`} d={areaPath(seg)} fill={`url(#${gid})`} />
      ))}
      {segments.map((seg, si) => (
        <polyline key={`l${si}`} points={seg.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')}
          fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      ))}
      {points.map((p, i) => p.value != null && i !== lastIdx && (
        <circle key={`d${i}`} cx={xAt(i)} cy={yAt(p.value)} r="2.2" fill={color} opacity="0.85" />
      ))}
      {lastIdx >= 0 && (
        <g>
          <circle cx={xAt(lastIdx)} cy={yAt(points[lastIdx].value)} r="4.2"
            fill={color} stroke="var(--color-bg-secondary)" strokeWidth="2" />
          {formatValue && (
            <text x={xAt(lastIdx) - 6} y={yAt(points[lastIdx].value) - 8} textAnchor="end"
              className="fill-[var(--color-text-primary)]" style={{ fontSize: '10px', fontWeight: 700 }}>
              {formatValue(points[lastIdx].value)}
            </text>
          )}
        </g>
      )}
      {points.map((p, i) => labelIdx.has(i) && (
        <text key={`t${i}`} x={xAt(i)} y={H + 8} textAnchor="middle"
          className="fill-[var(--color-text-muted)]" style={{ fontSize: '9px' }}>{p.label}</text>
      ))}
    </svg>
  )
}

// Small up/down/flat trend pill for the forecast card.
const TrendBadge = ({ trend, t }) => {
  const map = {
    up: { arrow: '↑', cls: 'text-red-500 bg-red-500/10', label: t('charts.trendUp') || 'Rising' },
    down: { arrow: '↓', cls: 'text-emerald-500 bg-emerald-500/10', label: t('charts.trendDown') || 'Falling' },
    flat: { arrow: '→', cls: 'text-[var(--color-text-secondary)] bg-[var(--color-bg-tertiary)]', label: t('charts.trendFlat') || 'Stable' },
  }
  const s = map[trend] || map.flat
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${s.cls}`}>
      <span aria-hidden="true">{s.arrow}</span>{s.label}
    </span>
  )
}

// F11 — forward 12-month projected-cost bar chart with a monthly-budget line.
// One sequential hue for cost; over-budget months switch to a status colour
// (the "flag"), and the budget is a dashed reference line.
const ForecastChart = ({ buckets, budget, formatCurrency, monthShort, t }) => {
  const W = 340, H = 168, PL = 8, PR = 8, PT = 22, PB = 26
  const n = buckets.length
  if (!n) return null
  const maxVal = Math.max(budget || 0, ...buckets.map((b) => b.projected), 1)
  const cellW = (W - PL - PR) / n
  const xAt = (i) => PL + (i + 0.5) * cellW
  const bw = cellW * 0.62
  const yAt = (v) => (H - PB) - (Math.max(0, v) / maxVal) * (H - PT - PB)
  const budgetY = budget ? yAt(budget) : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
      aria-label={t('forecast.title') || 'Projected monthly costs'}>
      {buckets.map((b, i) => {
        const y = yAt(b.projected)
        const h = Math.max(0, (H - PB) - y)
        return (
          <rect key={`b${i}`} x={xAt(i) - bw / 2} y={y} width={bw} height={h} rx="2"
            fill={b.over_budget ? '#ef4444' : 'var(--color-accent)'}
            opacity={b.over_budget ? 0.92 : 0.85}>
            <title>{`${monthShort(b.month)}: ${formatCurrency(b.projected)}${b.over_budget ? ' — ' + (t('forecast.overBudget') || 'over budget') : ''}`}</title>
          </rect>
        )
      })}
      {budgetY != null && (
        <g>
          <line x1={PL} x2={W - PR} y1={budgetY} y2={budgetY}
            stroke="var(--color-text-muted)" strokeWidth="1.5" strokeDasharray="4 3" />
          <text x={W - PR} y={Math.max(8, budgetY - 3)} textAnchor="end"
            className="fill-[var(--color-text-muted)]" style={{ fontSize: '8px', fontWeight: 600 }}>
            {t('forecast.budgetLine') || 'Budget'} {formatCurrency(budget)}
          </text>
        </g>
      )}
      {buckets.map((b, i) => (i % 2 === 0) && (
        <text key={`t${i}`} x={xAt(i)} y={H - 8} textAnchor="middle"
          className="fill-[var(--color-text-muted)]" style={{ fontSize: '8px' }}>
          {monthShort(b.month)}
        </text>
      ))}
    </svg>
  )
}

export default function VehicleCharts() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency, language } = useCurrency()

  const [vehicle, setVehicle] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [forecast, setForecast] = useState(null)  // F11 — forward cost projection
  const [isLoading, setIsLoading] = useState(true)
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear())

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [vehicleRes, , timelineRes] = await Promise.all([
          vehicleApi.getById(id),
          vehicleApi.getStats(id),
          vehicleApi.getTimeline(id)
        ])
        setVehicle(vehicleRes.data)
        setTimeline(timelineRes.data?.entries || [])
      } catch (error) {
        console.error('Failed to fetch data:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [id, navigate])

  // Cost-trend / forecast analytics — fetched independently so a failure here
  // never breaks the rest of the Charts page (graceful degradation).
  useEffect(() => {
    let active = true
    vehicleApi.getCostAnalytics(id)
      .then((res) => { if (active) setAnalytics(res.data) })
      .catch((err) => { console.error('Failed to load cost analytics:', err) })
    return () => { active = false }
  }, [id])

  // F11 — forward-looking cost forecast (recurring + predictions vs budget).
  // Independent fetch so a failure never breaks the rest of the Charts page.
  useEffect(() => {
    let active = true
    vehicleApi.getForecast(id)
      .then((res) => { if (active) setForecast(res.data) })
      .catch((err) => { console.error('Failed to load forecast:', err) })
    return () => { active = false }
  }, [id])

  // Short, locale-aware month label from a 'YYYY-MM' key (numeric construction
  // avoids the date-only-string UTC parsing bug noted elsewhere in this file).
  const monthShort = (ym) => {
    const [y, m] = ym.split('-').map(Number)
    try {
      return new Date(y, m - 1, 1).toLocaleDateString(language || 'en', { month: 'short' })
    } catch {
      return ym
    }
  }

  // Per-distance values are small (e.g. 0.15) so they need decimals, unlike the
  // whole-currency formatCurrency used elsewhere on this page.
  const formatPerDistance = (v) => `${currency.symbol}${Number(v).toFixed(2)}`
  
  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return `${currency.symbol}0`
    return `${currency.symbol}${Number(amount).toFixed(0)}`
  }
  
  // Calculate chart data
  const chartData = useMemo(() => {
    if (!timeline.length) return null
    
    // I17 + B11: Use string slicing instead of new Date() on date-only strings.
    // new Date('2025-01-01') is parsed as UTC midnight, which shifts the date
    // in negative-offset timezones (e.g. UTC-5 sees 2024-12-31).
    const getYear  = (d) => parseInt(d.slice(0, 4), 10)
    const getMonth = (d) => parseInt(d.slice(5, 7), 10) - 1  // 0-indexed
    
    // Filter by selected year
    const yearEntries = timeline.filter(entry => getYear(entry.date) === selectedYear)
    
    // Get available years
    const years = [...new Set(timeline.map(e => getYear(e.date)))].sort((a, b) => b - a)
    
    // Expenses by category
    const categoryTotals = {
      fuel: 0,
      service: 0,
      repair: 0,
      tax: 0,
      parking: 0,
      other: 0
    }
    
    yearEntries.forEach(entry => {
      const cost = parseFloat(entry.cost) || 0
      if (categoryTotals.hasOwnProperty(entry.type)) {
        categoryTotals[entry.type] += cost
      } else {
        categoryTotals.other += cost
      }
    })
    
    const totalExpenses = Object.values(categoryTotals).reduce((a, b) => a + b, 0)
    
    // Monthly expenses
    const monthlyExpenses = Array(12).fill(0)
    yearEntries.forEach(entry => {
      const month = getMonth(entry.date)
      monthlyExpenses[month] += parseFloat(entry.cost) || 0
    })
    
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const monthlyData = monthlyExpenses.map((value, idx) => ({
      label: monthNames[idx],
      value,
      displayValue: formatCurrency(value)
    }))
    
    // Donut chart data
    const categoryColors = {
      fuel: '#f59e0b',
      service: '#3b82f6',
      repair: '#ef4444',
      tax: '#f43f5e',
      parking: '#a855f7',
      other: '#6b7280'
    }
    
    const donutData = Object.entries(categoryTotals)
      .filter(([_, value]) => value > 0)
      .map(([key, value]) => ({
        label: t(`charts.${key}`) || key.charAt(0).toUpperCase() + key.slice(1),
        value,
        color: categoryColors[key],
        percentage: totalExpenses > 0 ? ((value / totalExpenses) * 100).toFixed(1) : 0
      }))
    
    return {
      years,
      totalExpenses,
      categoryTotals,
      monthlyData,
      donutData,
      maxMonthly: Math.max(...monthlyExpenses)
    }
  }, [timeline, selectedYear, currency.symbol, t])
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-14 rounded-xl mb-4" />
        <div className="skeleton h-48 rounded-xl mb-4" />
        <div className="skeleton h-64 rounded-xl mb-4" />
        <div className="skeleton h-48 rounded-xl" />
      </div>
    )
  }
  
  return (
    <div className="pb-20">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => navigate(`/vehicles/${id}`)}
              className="p-2 -ml-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors"
            >
              {Icons.arrowBack}
            </button>
            <div>
              <h1 className="text-lg font-semibold">{t('charts.title') || 'Charts'}</h1>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {vehicle?.make} {vehicle?.model}
              </p>
            </div>
          </div>
          
          {/* Year selector */}
          {chartData?.years?.length > 0 && (
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value))}
              className="px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border)] text-sm"
            >
              {chartData.years.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          )}
        </div>
      </div>
      
      {/* Content */}
      <div className="p-4 max-w-5xl mx-auto space-y-4">
        {/* Cost-per-distance trend + 12-month forecast (deterministic analytics).
            Shown above the year-scoped charts and independent of the year selector. */}
        {analytics && analytics.series?.some((s) => s.cost > 0) && (() => {
          const unit = analytics.distance_unit === 'miles' ? (t('common.miles') || 'mi') : (t('common.km') || 'km')
          const hasCpd = analytics.series.some((s) => s.cost_per_distance != null)
          const cpdPoints = analytics.series.map((s) => ({ label: monthShort(s.month), value: s.cost_per_distance }))
          return (
            <>
            {(analytics.converted === false || analytics.fx_applied) && (
              <p className="text-2xs text-[var(--color-text-muted)] flex items-start gap-1.5">
                <span aria-hidden="true">≈</span>
                <span>
                  {analytics.converted === false
                    ? (t('analytics.rateUnavailable') || 'Some amounts could not be converted — exchange rate unavailable.')
                    : (t('analytics.approxConverted') || 'Converted from mixed currencies at today’s rates.')}
                </span>
              </p>
            )}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Cost per distance */}
              <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
                <div className="flex items-start justify-between gap-3 mb-1">
                  <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">
                    {(t('charts.costPerDistance') || 'Cost per {unit}').replace('{unit}', unit)}
                  </h2>
                  {analytics.cost_per_distance_lifetime != null && (
                    <span className="text-lg font-bold whitespace-nowrap shrink-0">
                      {formatPerDistance(analytics.cost_per_distance_lifetime)}
                      <span className="text-xs text-[var(--color-text-secondary)] font-normal">/{unit}</span>
                    </span>
                  )}
                </div>
                <p className="text-2xs text-[var(--color-text-muted)] mb-4">
                  {t('charts.costPerDistanceDesc') || 'Lifetime average and recent monthly trend'}
                </p>
                {hasCpd ? (
                  <LineChart
                    points={cpdPoints}
                    formatValue={formatPerDistance}
                    ariaLabel={(t('charts.costPerDistance') || 'Cost per {unit}').replace('{unit}', unit)}
                  />
                ) : (
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {t('charts.costPerDistanceNoOdo') || 'Add odometer readings to your entries to see cost per distance over time.'}
                  </p>
                )}
              </div>

              {/* 12-month forecast */}
              {analytics.forecast && (
                <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
                  <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                    {t('charts.forecastTitle') || 'Predicted next 12 months'}
                  </h2>
                  <p className="text-2xs text-[var(--color-text-muted)] mb-4">
                    {(t('charts.forecastDesc') || 'Estimated from {n} months of history')
                      .replace('{n}', String(analytics.forecast.months_of_history))}
                  </p>
                  <div className="flex items-end justify-between gap-3 mb-4 flex-wrap">
                    <div>
                      <p className="text-3xl font-bold">{formatCurrency(analytics.forecast.projected_next_12_total)}</p>
                      <p className="text-xs text-[var(--color-text-secondary)]">
                        {(t('charts.forecastAvg') || '~{v}/month').replace('{v}', formatCurrency(analytics.forecast.avg_monthly))}
                      </p>
                    </div>
                    <TrendBadge trend={analytics.forecast.trend} t={t} />
                  </div>
                  <LineChart
                    points={analytics.forecast.monthly.map((mo) => ({ label: monthShort(mo.month), value: mo.projected_cost }))}
                    formatValue={formatCurrency}
                    ariaLabel={t('charts.forecastTitle') || 'Predicted next 12 months'}
                    color="#22c55e"
                  />
                  <p className="text-2xs text-[var(--color-text-muted)] mt-3">
                    {t('charts.forecastDisclaimer') || 'Estimate based on past spending — actual costs may vary.'}
                  </p>
                </div>
              )}
            </div>
            </>
          )
        })()}

        {/* F11 — forward 12-month projected-cost forecast (recurring + predictions
            vs monthly budget). Independent of the year selector; shown only when
            there is something to project. */}
        {forecast && forecast.buckets?.some((b) => b.projected > 0) && (() => {
          const total = forecast.buckets.reduce((a, b) => a + (b.projected || 0), 0)
          const overCount = forecast.buckets.filter((b) => b.over_budget).length
          return (
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <div className="flex items-start justify-between gap-3 mb-1">
                <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">
                  {t('forecast.title') || 'Projected costs — next 12 months'}
                </h2>
                <span className="text-lg font-bold whitespace-nowrap shrink-0">{formatCurrency(total)}</span>
              </div>
              <p className="text-2xs text-[var(--color-text-muted)] mb-4">
                {t('forecast.projected') || 'Recurring taxes, insurance, permits and predicted maintenance'}
              </p>

              {(forecast.converted === false || forecast.fx_applied) && (
                <p className="text-2xs text-[var(--color-text-muted)] flex items-start gap-1.5 mb-3">
                  <span aria-hidden="true">≈</span>
                  <span>
                    {forecast.converted === false
                      ? (t('analytics.rateUnavailable') || 'Some amounts could not be converted — exchange rate unavailable.')
                      : (t('analytics.approxConverted') || 'Converted from mixed currencies at today’s rates.')}
                  </span>
                </p>
              )}

              <ForecastChart
                buckets={forecast.buckets}
                budget={forecast.monthly_budget}
                formatCurrency={formatCurrency}
                monthShort={monthShort}
                t={t}
              />

              <div className="flex items-center justify-between flex-wrap gap-2 mt-3 text-2xs text-[var(--color-text-muted)]">
                {forecast.monthly_budget != null ? (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block w-3 border-t border-dashed border-[var(--color-text-muted)]" aria-hidden="true" />
                    {t('forecast.budgetLine') || 'Monthly budget'}: {formatCurrency(forecast.monthly_budget)}
                  </span>
                ) : <span />}
                {overCount > 0 && (
                  <span className="inline-flex items-center gap-1.5 text-red-500">
                    <span className="inline-block w-2.5 h-2.5 rounded-sm bg-red-500" aria-hidden="true" />
                    {(t('forecast.overBudget') || 'Over budget')} · {overCount}
                  </span>
                )}
              </div>
            </div>
          )
        })()}

        {/* I17: Two distinct empty states.
            Case 1 — no entries at all: chartData is null.
            Case 2 — entries exist in other years but not the selected year:
                     chartData is set but totalExpenses is 0; year selector
                     remains visible in the header so the user can switch. */}
        {!chartData ? (
          /* Case 1: vehicle has no expenses recorded at all */
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-[var(--color-bg-secondary)] flex items-center justify-center opacity-60">
              {Icons.calendar}
            </div>
            <h3 className="text-lg font-semibold mb-2">{t('charts.noData')}</h3>
            <p className="text-sm text-[var(--color-text-secondary)] max-w-xs leading-relaxed">
              {t('charts.noDataDesc')}
            </p>
          </div>
        ) : chartData.totalExpenses === 0 ? (
          /* Case 2: entries exist but none in the currently selected year */
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-[var(--color-bg-secondary)] flex items-center justify-center opacity-60">
              {Icons.calendar}
            </div>
            <h3 className="text-lg font-semibold mb-2">
              {t('charts.noDataForYear').replace('{year}', String(selectedYear))}
            </h3>
            <p className="text-sm text-[var(--color-text-secondary)] max-w-xs leading-relaxed">
              {t('charts.noDataForYearDesc')}
            </p>
          </div>
        ) : (
          <>
            {/* Total expenses card */}
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-2">
                {t('charts.totalExpenses') || 'Total Expenses'} ({selectedYear})
              </h2>
              <p className="text-3xl font-bold">{formatCurrency(chartData.totalExpenses)}</p>
            </div>
            
            {/* Category breakdown + monthly spend — two per row; stacks on phones */}
            <div className="grid md:grid-cols-2 gap-4">
            {/* Category breakdown donut */}
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-4">
                {t('charts.byCategory') || 'By Category'}
              </h2>

              <div className="flex flex-col items-center gap-4">
                <DonutChart 
                  data={chartData.donutData} 
                  total={chartData.totalExpenses}
                  centerLabel={formatCurrency(chartData.totalExpenses)}
                  totalLabel={t('common.total') || 'Total'}
                />
                
                {/* Legend */}
                <div className="flex-1 space-y-2">
                  {chartData.donutData.map((item, idx) => (
                    <div key={idx} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div 
                          className="w-3 h-3 rounded-full" 
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="text-sm">{item.label}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm font-medium">{formatCurrency(item.value)}</span>
                        <span className="text-xs text-[var(--color-text-secondary)] ml-2">
                          ({item.percentage}%)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            
            {/* Monthly expenses bar chart */}
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-4">
                {t('charts.monthlyExpenses') || 'Monthly Expenses'}
              </h2>
              
              <BarChart 
                data={chartData.monthlyData}
                maxValue={chartData.maxMonthly}
                color="bg-[var(--color-accent)]"
                label={t('charts.amount') || 'Amount'}
              />
            </div>
            </div>

            {/* Stats summary */}
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-4">
                {t('charts.quickStats') || 'Quick Stats'}
              </h2>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                  <div className="flex items-center gap-2 mb-1">
                    {Icons.fuel}
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {t('charts.fuelCost') || 'Fuel Cost'}
                    </span>
                  </div>
                  <p className="text-lg font-semibold text-amber-500">
                    {formatCurrency(chartData.categoryTotals.fuel)}
                  </p>
                </div>
                
                <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                  <div className="flex items-center gap-2 mb-1">
                    {Icons.wrench}
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {t('charts.serviceCost') || 'Service Cost'}
                    </span>
                  </div>
                  <p className="text-lg font-semibold text-blue-500">
                    {formatCurrency(chartData.categoryTotals.service)}
                  </p>
                </div>
                
                <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                  <div className="flex items-center gap-2 mb-1">
                    {Icons.tools}
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {t('charts.repairCost') || 'Repair Cost'}
                    </span>
                  </div>
                  <p className="text-lg font-semibold text-red-500">
                    {formatCurrency(chartData.categoryTotals.repair)}
                  </p>
                </div>
                
                <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-xl">
                  <div className="flex items-center gap-2 mb-1">
                    {Icons.receipt}
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {t('charts.taxCost') || 'Tax Cost'}
                    </span>
                  </div>
                  <p className="text-lg font-semibold text-rose-500">
                    {formatCurrency(chartData.categoryTotals.tax)}
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
