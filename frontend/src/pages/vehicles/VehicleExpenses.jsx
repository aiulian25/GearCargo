import { useState, useEffect, useMemo } from 'react'
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom'
import { vehicleApi, fuelApi, serviceApi, repairApi, taxApi, reminderApi, attachmentApi, insuranceApi } from '../../services/api'
import api from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { formatDate } from '../../utils/dateFormat'
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
}

// Donut Chart Component
const DonutChart = ({ data, centerText, centerSubtext }) => {
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
      <svg viewBox="0 0 200 200" className="w-full max-w-[280px] mx-auto">
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
              <span className="text-[var(--color-text-primary)]">{item.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[var(--color-accent)]">{item.value.toFixed(2)}</span>
              <span className="text-[var(--color-text-muted)]">({((item.value / (total || 1)) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Bar Chart Component
const BarChart = ({ data, categories, title }) => {
  const maxValue = Math.max(...data.map(d => d.total), 1)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  
  return (
    <div className="h-full flex flex-col">
      <h3 className="text-[var(--color-accent)] text-sm font-medium mb-4 text-center">{title}</h3>
      
      <div className="flex-1 flex items-end gap-1 px-2">
        {months.map((month, i) => {
          const monthData = data.find(d => d.month === i + 1) || { total: 0, breakdown: {} }
          const height = maxValue > 0 ? (monthData.total / maxValue) * 100 : 0
          
          return (
            <div key={month} className="flex-1 flex flex-col items-center">
              <div className="w-full flex flex-col justify-end h-32">
                {/* Stacked bars */}
                <div 
                  className="w-full rounded-t transition-all duration-300"
                  style={{ 
                    height: `${Math.max(height, 0)}%`,
                    minHeight: monthData.total > 0 ? '4px' : '0',
                    background: monthData.total > 0 
                      ? 'linear-gradient(to top, #22c55e, #84cc16, #facc15, #f97316, #ef4444)'
                      : 'transparent'
                  }}
                />
              </div>
              <span className="text-[10px] text-[var(--color-text-muted)] mt-1">{month}</span>
            </div>
          )
        })}
      </div>
      
      {/* Category badges */}
      <div className="flex flex-wrap gap-2 mt-4 justify-center">
        {categories.map((cat, i) => (
          <span 
            key={i}
            className="px-2 py-0.5 rounded text-xs font-medium"
            style={{ backgroundColor: cat.color, color: '#fff' }}
          >
            {cat.label}
          </span>
        ))}
      </div>
    </div>
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
        ? `${tabColors[tabId] || 'bg-[var(--color-accent)]'} text-white` 
        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] hover:bg-[var(--color-bg-secondary)]'
    }`}
  >
    <span className={active ? 'text-white' : 'text-[var(--color-text-secondary)]'}>{icon}</span>
    <span>{label}</span>
    {count !== undefined && count > 0 && (
      <span className={`text-xs ${active ? 'text-white/80' : 'text-[var(--color-text-muted)]'}`}>({count})</span>
    )}
  </button>
)

const VALID_TABS = ['fuel', 'service', 'tax', 'parking', 'repair', 'insurance', 'todo', 'reminder']

export default function VehicleExpenses() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { t } = useTranslation()
  const { formatCurrency } = useCurrency()
  
  const [vehicle, setVehicle] = useState(null)
  const [loading, setLoading] = useState(true)
  const initialTab = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState(VALID_TABS.includes(initialTab) ? initialTab : 'fuel')
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear())
  
  // Attachment viewer state
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewerAttachments, setViewerAttachments] = useState([])
  const [viewerInitialIndex, setViewerInitialIndex] = useState(0)
  
  // Data states
  const [fuelEntries, setFuelEntries] = useState([])
  const [serviceEntries, setServiceEntries] = useState([])
  const [taxEntries, setTaxEntries] = useState([])
  const [parkingEntries, setParkingEntries] = useState([])
  const [repairEntries, setRepairEntries] = useState([])
  const [insuranceEntries, setInsuranceEntries] = useState([])
  const [todoEntries, setTodoEntries] = useState([])
  const [reminderEntries, setReminderEntries] = useState([])

  useEffect(() => {
    fetchAllData()
  }, [id])

  const fetchAllData = async () => {
    try {
      setLoading(true)
      
      // Fetch each API separately with error handling
      const vehicleRes = await vehicleApi.getById(id)
      setVehicle(vehicleRes.data)
      
      // Fetch all data with individual error handling
      const results = await Promise.allSettled([
        fuelApi.getByVehicle(id),
        serviceApi.getByVehicle(id),
        repairApi.getByVehicle(id),
        taxApi.getAll(id),
        api.get(`/parking?vehicle_id=${id}`),
        reminderApi.getAll(id),
        api.get(`/todos?vehicle_id=${id}`),
        insuranceApi.getAll(id),
      ])
      
      // Process results with proper fallbacks
      const [fuelRes, serviceRes, repairRes, taxRes, parkingRes, reminderRes, todoRes, insuranceRes] = results
      
      if (fuelRes.status === 'fulfilled') {
        setFuelEntries(fuelRes.value.data.entries || fuelRes.value.data || [])
      }
      if (serviceRes.status === 'fulfilled') {
        setServiceEntries(serviceRes.value.data.entries || serviceRes.value.data || [])
      }
      if (repairRes.status === 'fulfilled') {
        setRepairEntries(repairRes.value.data.entries || repairRes.value.data || [])
      }
      if (taxRes.status === 'fulfilled') {
        setTaxEntries(taxRes.value.data.entries || taxRes.value.data || [])
      }
      if (parkingRes.status === 'fulfilled') {
        setParkingEntries(parkingRes.value.data.entries || parkingRes.value.data || [])
      }
      if (reminderRes.status === 'fulfilled') {
        setReminderEntries(reminderRes.value.data.reminders || reminderRes.value.data || [])
      }
      if (todoRes.status === 'fulfilled') {
        setTodoEntries(todoRes.value.data.todos || todoRes.value.data || [])
      }
      if (insuranceRes.status === 'fulfilled') {
        setInsuranceEntries(insuranceRes.value.data.policies || insuranceRes.value.data || [])
      }
      
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }

  // Calculate totals by category filtered to selectedYear
  const categoryTotals = useMemo(() => {
    const inYear = (dateStr) => dateStr && new Date(dateStr).getFullYear() === selectedYear

    const fuelTotal = fuelEntries
      .filter(e => inYear(e.date))
      .reduce((sum, e) => sum + (parseFloat(e.total_price) || 0), 0)
    const serviceTotal = serviceEntries
      .filter(e => inYear(e.date))
      .reduce((sum, e) => sum + (parseFloat(e.amount) || 0), 0)
    const taxTotal = taxEntries
      .filter(e => inYear(e.date))
      .reduce((sum, e) => sum + (parseFloat(e.amount) || 0), 0)
    const parkingTotal = parkingEntries
      .filter(e => inYear(e.date))
      .reduce((sum, e) => sum + (parseFloat(e.amount) || 0), 0)
    const repairTotal = repairEntries
      .filter(e => inYear(e.date))
      .reduce((sum, e) => sum + (parseFloat(e.amount) || 0), 0)

    // Insurance: count actual payments made in selectedYear (mirrors monthlyData logic)
    const today = new Date()
    const currentYear = today.getFullYear()
    let insuranceTotal = 0
    insuranceEntries.forEach(policy => {
      const premium = parseFloat(policy.premium) || 0
      const startDate = policy.start_date ? new Date(policy.start_date) : null
      const endDate = policy.end_date ? new Date(policy.end_date) : null
      const frequency = policy.payment_frequency || 'annual'
      if (!startDate) return

      if (frequency === 'annual' || frequency === 'yearly') {
        if (startDate.getFullYear() === selectedYear) insuranceTotal += premium
      } else if (frequency === 'monthly') {
        const paymentDay = startDate.getDate()
        const yearStart = new Date(selectedYear, 0, 1)
        const yearEnd = endDate
          ? new Date(Math.min(endDate.getTime(), new Date(selectedYear, 11, 31).getTime()))
          : new Date(selectedYear, 11, 31)
        const periodStart = new Date(Math.max(startDate.getTime(), yearStart.getTime()))
        let periodEnd = yearEnd
        if (selectedYear === currentYear) {
          const paidThroughMonth = today.getDate() >= paymentDay ? today.getMonth() : today.getMonth() - 1
          const cappedDate = new Date(selectedYear, paidThroughMonth, 28)
          if (cappedDate < periodEnd) periodEnd = cappedDate
        }
        if (startDate.getFullYear() <= selectedYear && (!endDate || endDate.getFullYear() >= selectedYear) && periodStart <= periodEnd) {
          const months = periodEnd.getMonth() - periodStart.getMonth() + 1
          insuranceTotal += premium * Math.max(0, months)
        }
      } else if (frequency === 'quarterly') {
        const startMonth = startDate.getMonth()
        for (let q = 0; q < 4; q++) {
          const paymentMonth = (startMonth + q * 3) % 12
          const paymentYear = startDate.getFullYear() + Math.floor((startMonth + q * 3) / 12)
          if (paymentYear === selectedYear && (!endDate || new Date(paymentYear, paymentMonth, 1) <= endDate)) {
            insuranceTotal += premium
          }
        }
      } else if (frequency === 'semi-annual' || frequency === 'semi_annual') {
        const startMonth = startDate.getMonth()
        for (let s = 0; s < 2; s++) {
          const paymentMonth = (startMonth + s * 6) % 12
          const paymentYear = startDate.getFullYear() + Math.floor((startMonth + s * 6) / 12)
          if (paymentYear === selectedYear && (!endDate || new Date(paymentYear, paymentMonth, 1) <= endDate)) {
            insuranceTotal += premium
          }
        }
      }
    })

    return { fuelTotal, serviceTotal, taxTotal, parkingTotal, repairTotal, insuranceTotal }
  }, [fuelEntries, serviceEntries, taxEntries, parkingEntries, repairEntries, insuranceEntries, selectedYear])

  // Donut chart data
  const donutData = [
    { label: t('expenses.fuel') || 'Fuel', value: categoryTotals.fuelTotal, color: '#3b82f6' },
    { label: t('expenses.service') || 'Service', value: categoryTotals.serviceTotal, color: '#22c55e' },
    { label: t('expenses.tax') || 'Tax', value: categoryTotals.taxTotal, color: '#a855f7' },
    { label: t('expenses.parking') || 'Parking', value: categoryTotals.parkingTotal, color: '#f59e0b' },
    { label: t('expenses.repair') || 'Repairs', value: categoryTotals.repairTotal, color: '#ef4444' },
    { label: t('expenses.insurance') || 'Insurance', value: categoryTotals.insuranceTotal, color: '#10b981' },
  ]

  // Monthly expenses calculation
  const monthlyData = useMemo(() => {
    const months = Array.from({ length: 12 }, (_, i) => ({ month: i + 1, total: 0, breakdown: {} }))
    
    const addToMonth = (entries, key, getAmount, getDate) => {
      entries.forEach(entry => {
        const dateStr = getDate(entry)
        if (!dateStr) return
        const date = new Date(dateStr)
        if (date.getFullYear() === selectedYear) {
          const monthIndex = date.getMonth()
          const amount = getAmount(entry)
          months[monthIndex].total += amount
          months[monthIndex].breakdown[key] = (months[monthIndex].breakdown[key] || 0) + amount
        }
      })
    }
    
    addToMonth(fuelEntries, 'fuel', e => parseFloat(e.total_price) || 0, e => e.date)
    addToMonth(serviceEntries, 'service', e => parseFloat(e.amount) || 0, e => e.date)
    addToMonth(taxEntries, 'tax', e => parseFloat(e.amount) || 0, e => e.date)
    addToMonth(parkingEntries, 'parking', e => parseFloat(e.amount) || 0, e => e.date)
    addToMonth(repairEntries, 'repair', e => parseFloat(e.amount) || 0, e => e.date)
    
    // Handle insurance based on payment frequency
    insuranceEntries.forEach(policy => {
      const premium = parseFloat(policy.premium) || 0
      const startDate = policy.start_date ? new Date(policy.start_date) : null
      const endDate = policy.end_date ? new Date(policy.end_date) : null
      const frequency = policy.payment_frequency || 'annual'
      
      if (!startDate) return
      
      if (frequency === 'annual' || frequency === 'yearly') {
        // Annual: add full amount on start date
        if (startDate.getFullYear() === selectedYear) {
          const monthIndex = startDate.getMonth()
          months[monthIndex].total += premium
          months[monthIndex].breakdown['insurance'] = (months[monthIndex].breakdown['insurance'] || 0) + premium
        }
      } else if (frequency === 'monthly') {
        // Monthly: add premium only on the payment day each month (same day-of-month as start date)
        const today = new Date()
        const currentYear = today.getFullYear()
        const paymentDay = startDate.getDate()
        const yearStart = new Date(selectedYear, 0, 1)
        const yearEnd = endDate
          ? new Date(Math.min(endDate.getTime(), new Date(selectedYear, 11, 31).getTime()))
          : new Date(selectedYear, 11, 31)
        const periodStart = new Date(Math.max(startDate.getTime(), yearStart.getTime()))
        let periodEnd = yearEnd
        // For current year, only count months where the payment day has already passed
        if (selectedYear === currentYear) {
          const paidThroughMonth = today.getDate() >= paymentDay ? today.getMonth() : today.getMonth() - 1
          const cappedDate = new Date(selectedYear, paidThroughMonth, 28)
          if (cappedDate < periodEnd) periodEnd = cappedDate
        }
        if (periodStart <= periodEnd && startDate.getFullYear() <= selectedYear && (!endDate || endDate.getFullYear() >= selectedYear)) {
          for (let m = periodStart.getMonth(); m <= periodEnd.getMonth(); m++) {
            months[m].total += premium
            months[m].breakdown['insurance'] = (months[m].breakdown['insurance'] || 0) + premium
          }
        }
      } else if (frequency === 'quarterly') {
        // Quarterly: add premium every 3 months from start date
        const startMonth = startDate.getMonth()
        for (let q = 0; q < 4; q++) {
          const paymentMonth = (startMonth + q * 3) % 12
          const paymentYear = startDate.getFullYear() + Math.floor((startMonth + q * 3) / 12)
          if (paymentYear === selectedYear && (!endDate || new Date(paymentYear, paymentMonth, 1) <= endDate)) {
            months[paymentMonth].total += premium
            months[paymentMonth].breakdown['insurance'] = (months[paymentMonth].breakdown['insurance'] || 0) + premium
          }
        }
      } else if (frequency === 'semi-annual' || frequency === 'semi_annual') {
        // Semi-annual: add premium every 6 months from start date
        const startMonth = startDate.getMonth()
        for (let s = 0; s < 2; s++) {
          const paymentMonth = (startMonth + s * 6) % 12
          const paymentYear = startDate.getFullYear() + Math.floor((startMonth + s * 6) / 12)
          if (paymentYear === selectedYear && (!endDate || new Date(paymentYear, paymentMonth, 1) <= endDate)) {
            months[paymentMonth].total += premium
            months[paymentMonth].breakdown['insurance'] = (months[paymentMonth].breakdown['insurance'] || 0) + premium
          }
        }
      }
    })
    
    return months
  }, [fuelEntries, serviceEntries, taxEntries, parkingEntries, repairEntries, insuranceEntries, selectedYear])

  const categories = [
    { label: t('expenses.fuel') || 'Fuel', color: '#3b82f6' },
    { label: t('expenses.service') || 'Service', color: '#22c55e' },
    { label: t('expenses.tax') || 'Tax', color: '#a855f7' },
    { label: t('expenses.parking') || 'Parking', color: '#f59e0b' },
    { label: t('expenses.repair') || 'Repairs', color: '#ef4444' },
    { label: t('expenses.insurance') || 'Insurance', color: '#10b981' },
  ]

  // Available years
  const years = useMemo(() => {
    const allDates = [
      ...fuelEntries.map(e => e.date),
      ...serviceEntries.map(e => e.date),
      ...taxEntries.map(e => e.date),
      ...parkingEntries.map(e => e.date),
      ...repairEntries.map(e => e.date),
      ...insuranceEntries.map(e => e.start_date),
    ].filter(Boolean)
    
    const yearSet = new Set(allDates.map(d => new Date(d).getFullYear()))
    yearSet.add(new Date().getFullYear())
    return Array.from(yearSet).sort((a, b) => b - a)
  }, [fuelEntries, serviceEntries, taxEntries, parkingEntries, repairEntries, insuranceEntries])

  // formatDate imported from utils/dateFormat

  const handleCancelRecurring = async (type, entryId) => {
    const msg = type === 'insurance'
      ? 'Cancel this insurance policy? This will stop future recurring costs and set the end date to today.'
      : 'Cancel recurring road tax? Future auto-generated entries will be stopped.'
    if (!confirm(msg)) return
    try {
      if (type === 'insurance') {
        const res = await insuranceApi.cancel(entryId)
        setInsuranceEntries(prev => prev.map(e => e.id === entryId ? res.data.policy : e))
      } else if (type === 'tax') {
        const res = await taxApi.cancel(entryId)
        setTaxEntries(prev => prev.map(e => e.id === entryId ? res.data.entry : e))
      }
    } catch (error) {
      console.error('Failed to cancel recurring:', error)
    }
  }

  const handleDelete = async (type, entryId) => {
    if (!confirm(t('common.confirmDelete') || 'Are you sure you want to delete this entry?')) return
    
    try {
      switch (type) {
        case 'fuel':
          await fuelApi.delete(entryId)
          setFuelEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'service':
          await serviceApi.delete(entryId)
          setServiceEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'repair':
          await repairApi.delete(entryId)
          setRepairEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'tax':
          await taxApi.delete(entryId)
          setTaxEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'parking':
          await api.delete(`/parking/${entryId}`)
          setParkingEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'reminder':
          await reminderApi.delete(entryId)
          setReminderEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'todo':
          await api.delete(`/todos/${entryId}`)
          setTodoEntries(prev => prev.filter(e => e.id !== entryId))
          break
        case 'insurance':
          await insuranceApi.delete(entryId)
          setInsuranceEntries(prev => prev.filter(e => e.id !== entryId))
          break
      }
    } catch (error) {
      console.error('Failed to delete:', error)
    }
  }

  // Navigate to edit page for entry
  const handleEdit = (type, entryId) => {
    const editRoutes = {
      fuel: `/vehicles/${id}/fuel/add?edit=${entryId}`,
      service: `/vehicles/${id}/service/add?edit=${entryId}`,
      repair: `/vehicles/${id}/repair/add?edit=${entryId}`,
      tax: `/vehicles/${id}/tax/add?edit=${entryId}`,
      parking: `/vehicles/${id}/parking/add?edit=${entryId}`,
      reminder: `/vehicles/${id}/reminder/add?edit=${entryId}`,
      todo: `/vehicles/${id}/todo/add?edit=${entryId}`,
      insurance: `/vehicles/${id}/insurance/add?edit=${entryId}`,
    }
    navigate(editRoutes[type])
  }

  // Open attachment viewer
  const openAttachmentViewer = (attachments, index = 0) => {
    if (attachments && attachments.length > 0) {
      setViewerAttachments(attachments)
      setViewerInitialIndex(index)
      setViewerOpen(true)
    }
  }

  // Render attachment button for entries
  const renderAttachmentButton = (entry) => {
    const attachments = entry.attachments || []
    if (attachments.length === 0) return <span className="text-[var(--color-text-muted)]">-</span>
    
    return (
      <button
        onClick={() => openAttachmentViewer(attachments)}
        className="flex items-center gap-1 text-yellow-500 hover:text-yellow-400 transition-colors"
        title={`${attachments.length} ${t('common.attachment') || 'attachment'}${attachments.length > 1 ? 's' : ''}`}
      >
        {Icons.eye}
        <span className="text-xs">({attachments.length})</span>
      </button>
    )
  }

  // Tab definitions
  const tabs = [
    { id: 'fuel', label: t('expenses.fuel') || 'Fuel', icon: Icons.fuel, count: fuelEntries.length },
    { id: 'service', label: t('expenses.service') || 'Service', icon: Icons.service, count: serviceEntries.length },
    { id: 'tax', label: t('expenses.tax') || 'Tax', icon: Icons.tax, count: taxEntries.length },
    { id: 'parking', label: t('expenses.parking') || 'Parking', icon: Icons.parking, count: parkingEntries.length },
    { id: 'repair', label: t('expenses.repair') || 'Repairs', icon: Icons.repair, count: repairEntries.length },
    { id: 'insurance', label: t('expenses.insurance') || 'Insurance', icon: Icons.shield, count: insuranceEntries.length },
    { id: 'todo', label: t('expenses.todos') || 'Todos', icon: Icons.todo, count: todoEntries.length },
    { id: 'reminder', label: t('expenses.reminders') || 'Reminders', icon: Icons.reminder, count: reminderEntries.length },
  ]

  // Render table based on active tab
  const renderTable = () => {
    switch (activeTab) {
      case 'fuel':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
                <th className="pb-3 px-4">{t('common.date') || 'Date'}</th>
                <th className="pb-3 px-4">{t('addFuel.odometer') || 'Odometer'}</th>
                <th className="pb-3 px-4">{t('addFuel.liters') || 'Liters'}</th>
                <th className="pb-3 px-4">{t('addFuel.pricePerLiter') || 'Price per Liter'}</th>
                <th className="pb-3 px-4">{t('addFuel.totalCost') || 'Total Price'}</th>
                <th className="pb-3 px-4">{t('addFuel.fuelType') || 'Fuel Type'}</th>
                <th className="pb-3 px-4">{t('addFuel.station') || 'Station'}</th>
                <th className="pb-3 px-4">{t('common.attachment') || 'Attachment'}</th>
                <th className="pb-3 px-4">{t('common.actions') || 'Actions'}</th>
              </tr>
            </thead>
            <tbody>
              {fuelEntries.map(entry => (
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">{entry.liters} L</td>
                  <td className="py-3 px-4 text-[var(--color-accent)]">{formatCurrency(entry.price_per_liter)}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.total_price)}</td>
                  <td className="py-3 px-4">{entry.fuel_type || '-'}</td>
                  <td className="py-3 px-4">{entry.station || '-'}</td>
                  <td className="py-3 px-4">
                    {renderAttachmentButton(entry)}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('fuel', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
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
                <tr><td colSpan={9} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'service':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{(entry.service_types?.length > 0 ? entry.service_types.map(st => st.replace(/_/g, ' ')).join(', ') : entry.service_type || entry.title || '-')}</td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} {vehicle?.distance_unit || 'km'}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.parts_cost || 0)}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.labor_cost || 0)}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.amount)}</td>
                  <td className="py-3 px-4">{entry.provider || '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('service', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
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
                <tr><td colSpan={9} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'tax':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.tax_type || entry.title || '-'}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.amount)}</td>
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
                  <td className="py-3 px-4">{entry.recurring ? '✓' : '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('tax', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      {entry.recurring && (
                        <button
                          onClick={() => handleCancelRecurring('tax', entry.id)}
                          className="text-orange-500 hover:text-orange-400 p-1"
                          title="Cancel recurring tax (stop future auto-generated entries)"
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
                <tr><td colSpan={8} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'parking':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.location || '-'}</td>
                  <td className="py-3 px-4">{entry.parking_type || '-'}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.amount)}</td>
                  <td className="py-3 px-4">{entry.duration || '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('parking', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
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
                <tr><td colSpan={7} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'repair':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{formatDate(entry.date)}</td>
                  <td className="py-3 px-4">{entry.repair_type || entry.title || '-'}</td>
                  <td className="py-3 px-4">{entry.odometer?.toLocaleString()} km</td>
                  <td className="py-3 px-4">{formatCurrency(entry.parts_cost || 0)}</td>
                  <td className="py-3 px-4">{formatCurrency(entry.labor_cost || 0)}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.amount)}</td>
                  <td className="py-3 px-4">{entry.provider || '-'}</td>
                  <td className="py-3 px-4">{renderAttachmentButton(entry)}</td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('repair', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
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
                <tr><td colSpan={9} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'insurance':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
              {insuranceEntries.map(entry => (
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4 font-medium">{entry.provider}</td>
                  <td className="py-3 px-4">{entry.policy_number || '-'}</td>
                  <td className="py-3 px-4 capitalize">{entry.policy_type?.replace('_', ' ') || '-'}</td>
                  <td className="py-3 px-4 text-[var(--color-accent)] font-medium">{formatCurrency(entry.premium)}</td>
                  <td className="py-3 px-4 capitalize">{entry.payment_frequency || '-'}</td>
                  <td className="py-3 px-4">{formatDate(entry.start_date)}</td>
                  <td className="py-3 px-4">{formatDate(entry.end_date)}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      entry.status === 'active' ? 'bg-green-500/20 text-green-400' :
                      entry.status === 'expired' ? 'bg-red-500/20 text-red-400' :
                      'bg-gray-500/20 text-[var(--color-text-secondary)]'
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
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
                        title={t('common.edit') || 'Edit'}
                      >
                        {Icons.edit}
                      </button>
                      {entry.status === 'active' && (
                        <button
                          onClick={() => handleCancelRecurring('insurance', entry.id)}
                          className="text-orange-500 hover:text-orange-400 p-1"
                          title="Cancel insurance (stop recurring costs)"
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
              ))}
              {insuranceEntries.length === 0 && (
                <tr><td colSpan={10} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'todo':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
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
                      entry.completed ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-[var(--color-text-secondary)]'
                    }`}>
                      {entry.completed ? t('common.completed') || 'Completed' : t('common.pending') || 'Pending'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => handleEdit('todo', entry.id)}
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
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
                <tr><td colSpan={6} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
              )}
            </tbody>
          </table>
        )

      case 'reminder':
        return (
          <table className="w-full">
            <thead>
              <tr className="text-left text-[var(--color-text-secondary)] text-sm border-b border-[var(--color-border)]">
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
                <tr key={entry.id} className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)]">
                  <td className="py-3 px-4">{entry.title}</td>
                  <td className="py-3 px-4">{entry.reminder_type || '-'}</td>
                  <td className="py-3 px-4">{formatDate(entry.due_date)}</td>
                  <td className="py-3 px-4">{entry.due_mileage?.toLocaleString() || '-'} km</td>
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
                        className="text-[var(--color-accent)] hover:text-[var(--color-accent)] p-1"
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
                <tr><td colSpan={6} className="py-8 text-center text-[var(--color-text-muted)]">{t('expenses.noEntries') || 'No entries found'}</td></tr>
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] pb-20">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)]">
        <div className="flex items-center gap-3 p-4">
          <button 
            onClick={() => navigate(`/vehicles/${id}`)}
            className="p-2 -ml-2 rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors"
          >
            {Icons.arrowBack}
          </button>
          <div>
            <h1 className="text-lg font-semibold">{t('expenses.expensesManager') || 'Expenses Manager'}</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model}
            </p>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-6">
      {/* Top Section - Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Donut Chart Card */}
        <div className="bg-[var(--color-bg-secondary)] rounded-xl p-6 border border-[var(--color-border)]">
          <DonutChart 
            data={donutData}
            centerText={`${vehicle?.year || ''} ${vehicle?.make || ''}`}
            centerSubtext={vehicle?.model || ''}
          />
        </div>

        {/* Bar Chart Card */}
        <div className="bg-[var(--color-bg-secondary)] rounded-xl p-6 border border-[var(--color-border)]">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[var(--color-text-secondary)] text-sm">{t('expenses.selectYear') || 'Select Year'}</span>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-1 text-[var(--color-text-primary)]"
            >
              {years.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
          <BarChart data={monthlyData} categories={categories} title={t('charts.monthlyExpenses') || 'Monthly Expenses'} />
        </div>
      </div>

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

      {/* Data Table */}
      <div className="bg-[var(--color-bg-secondary)] rounded-xl border border-[var(--color-border)] overflow-x-auto">
        {renderTable()}
      </div>
      </div>

      {/* Attachment Viewer Modal */}
      <AttachmentViewer
        attachments={viewerAttachments}
        initialIndex={viewerInitialIndex}
        isOpen={viewerOpen}
        onClose={() => setViewerOpen(false)}
      />
    </div>
  )
}
