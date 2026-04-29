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

export default function VehicleCharts() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  
  const [vehicle, setVehicle] = useState(null)
  const [timeline, setTimeline] = useState([])
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
      <div className="p-4 space-y-6">
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
            
            {/* Category breakdown donut */}
            <div className="bg-[var(--color-bg-secondary)] rounded-2xl p-6">
              <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-4">
                {t('charts.byCategory') || 'By Category'}
              </h2>
              
              <div className="flex flex-col sm:flex-row items-center gap-6">
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
