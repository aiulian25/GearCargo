import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { calendarApi, vehicleApi } from '../../services/api'
import { Skeleton, SkeletonScreen } from '../../components/ui/Skeleton'
import toast from 'react-hot-toast'

// Entry type icons and colors
const entryConfig = {
  fuel: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h10.5M5.25 21V6a2.25 2.25 0 012.25-2.25h3a2.25 2.25 0 012.25 2.25v15m-7.5-9h7.5m4.5-1.5v9a1.5 1.5 0 001.5 1.5h.75a.75.75 0 00.75-.75v-6a.75.75 0 00-.75-.75h-.75m0 0V6.75a.75.75 0 01.75-.75h.75a2.25 2.25 0 012.25 2.25v1.5" />
      </svg>
    ),
    color: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    dotColor: 'bg-amber-500',
  },
  service: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
      </svg>
    ),
    color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    dotColor: 'bg-blue-500',
  },
  repair: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75a4.5 4.5 0 01-4.884 4.484c-1.076-.091-2.264.071-2.95.904l-7.152 8.684a2.548 2.548 0 11-3.586-3.586l8.684-7.152c.833-.686.995-1.874.904-2.95a4.5 4.5 0 016.336-4.486l-3.276 3.276a3.004 3.004 0 002.25 2.25l3.276-3.276c.256.565.398 1.192.398 1.852z" />
      </svg>
    ),
    color: 'bg-red-500/20 text-red-400 border-red-500/30',
    dotColor: 'bg-red-500',
  },
  tax: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
      </svg>
    ),
    color: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    dotColor: 'bg-purple-500',
  },
  parking: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12" />
      </svg>
    ),
    color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    dotColor: 'bg-cyan-500',
  },
  insurance: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
    color: 'bg-green-500/20 text-green-400 border-green-500/30',
    dotColor: 'bg-green-500',
  },
  reminder: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
      </svg>
    ),
    color: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    dotColor: 'bg-orange-500',
  },
  todo: {
    icon: (
      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
    dotColor: 'bg-pink-500',
  },
}

// Helper to get days in month
const getDaysInMonth = (year, month) => new Date(year, month + 1, 0).getDate()

// Helper to get first day of month (0 = Sunday)
const getFirstDayOfMonth = (year, month) => new Date(year, month, 1).getDay()

export default function Calendar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  
  const [currentDate, setCurrentDate] = useState(new Date())
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [vehicles, setVehicles] = useState([])
  const [selectedVehicle, setSelectedVehicle] = useState(null)
  const [selectedDate, setSelectedDate] = useState(null)
  const [showDayModal, setShowDayModal] = useState(false)
  const [filterType, setFilterType] = useState('all')
  
  const year = currentDate.getFullYear()
  const month = currentDate.getMonth()
  
  // Fetch vehicles
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        setVehicles(response.data.vehicles || [])
      } catch (error) {
        console.error('Failed to load vehicles:', error)
      }
    }
    fetchVehicles()
  }, [])
  
  // Fetch calendar entries
  useEffect(() => {
    const fetchEntries = async () => {
      setLoading(true)
      try {
        // Get entries for current month and surrounding months
        const startDate = new Date(year, month - 1, 1).toISOString().split('T')[0]
        const endDate = new Date(year, month + 2, 0).toISOString().split('T')[0]
        
        const response = await calendarApi.getEntries(startDate, endDate, selectedVehicle)
        setEntries(response.data.entries || [])
      } catch (error) {
        console.error('Failed to load calendar entries:', error)
        toast.error(t('calendar.loadError'))
      } finally {
        setLoading(false)
      }
    }
    fetchEntries()
  }, [year, month, selectedVehicle, t])
  
  // Group entries by date
  const entriesByDate = useMemo(() => {
    const grouped = {}
    entries.forEach(entry => {
      const date = entry.date
      if (!grouped[date]) {
        grouped[date] = []
      }
      grouped[date].push(entry)
    })
    return grouped
  }, [entries])
  
  // Get entries for selected date
  const selectedDateEntries = useMemo(() => {
    if (!selectedDate) return []
    let filtered = entriesByDate[selectedDate] || []
    if (filterType !== 'all') {
      filtered = filtered.filter(e => e.type === filterType)
    }
    return filtered
  }, [selectedDate, entriesByDate, filterType])
  
  // Generate calendar grid
  const calendarDays = useMemo(() => {
    const daysInMonth = getDaysInMonth(year, month)
    const firstDay = getFirstDayOfMonth(year, month)
    const days = []
    
    // Previous month days
    const prevMonthDays = getDaysInMonth(year, month - 1)
    for (let i = firstDay - 1; i >= 0; i--) {
      days.push({
        day: prevMonthDays - i,
        isCurrentMonth: false,
        date: new Date(year, month - 1, prevMonthDays - i).toISOString().split('T')[0]
      })
    }
    
    // Current month days
    for (let i = 1; i <= daysInMonth; i++) {
      const date = new Date(year, month, i).toISOString().split('T')[0]
      days.push({
        day: i,
        isCurrentMonth: true,
        date,
        isToday: date === new Date().toISOString().split('T')[0]
      })
    }
    
    // Next month days
    const remainingDays = 42 - days.length // 6 rows x 7 days
    for (let i = 1; i <= remainingDays; i++) {
      days.push({
        day: i,
        isCurrentMonth: false,
        date: new Date(year, month + 1, i).toISOString().split('T')[0]
      })
    }
    
    return days
  }, [year, month])
  
  // Navigate months
  const goToPrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1))
  }
  
  const goToNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1))
  }
  
  const goToToday = () => {
    setCurrentDate(new Date())
  }
  
  // Handle day click
  const handleDayClick = (date) => {
    setSelectedDate(date)
    setShowDayModal(true)
  }
  
  // Get unique entry types for a date (for dots display)
  const getEntryTypesForDate = (date) => {
    const dateEntries = entriesByDate[date] || []
    const types = [...new Set(dateEntries.map(e => e.type))]
    return types.slice(0, 4) // Max 4 dots
  }
  
  // Format month name
  const monthNames = [
    t('calendar.months.january'), t('calendar.months.february'), t('calendar.months.march'),
    t('calendar.months.april'), t('calendar.months.may'), t('calendar.months.june'),
    t('calendar.months.july'), t('calendar.months.august'), t('calendar.months.september'),
    t('calendar.months.october'), t('calendar.months.november'), t('calendar.months.december')
  ]
  
  // Day names
  const dayNames = [
    t('days.sun'), t('days.mon'), t('days.tue'), t('days.wed'),
    t('days.thu'), t('days.fri'), t('days.sat')
  ]
  
  // Entry type labels for filter
  const entryTypes = [
    { key: 'all', label: t('calendar.filter.all') },
    { key: 'fuel', label: t('calendar.filter.fuel') },
    { key: 'service', label: t('calendar.filter.service') },
    { key: 'repair', label: t('calendar.filter.repair') },
    { key: 'tax', label: t('calendar.filter.tax') },
    { key: 'parking', label: t('calendar.filter.parking') },
    { key: 'insurance', label: t('calendar.filter.insurance') },
    { key: 'reminder', label: t('calendar.filter.reminder') },
    { key: 'todo', label: t('calendar.filter.todo') },
  ]
  
  return (
    <div className="px-4 py-4 pb-20">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">
          {t('calendar.title')}
        </h1>
        <p className="text-sm text-[var(--color-text-muted)]">
          {t('calendar.subtitle')}
        </p>
      </div>
      
      {/* Vehicle Filter */}
      <div className="mb-4">
        <select
          value={selectedVehicle || ''}
          onChange={(e) => setSelectedVehicle(e.target.value || null)}
          className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">{t('calendar.allVehicles')}</option>
          {vehicles.map(v => (
            <option key={v.id} value={v.id}>{v.name}</option>
          ))}
        </select>
      </div>
      
      {/* Calendar Navigation */}
      <div className="flex items-center justify-between mb-4 bg-[var(--color-bg-card)] rounded-xl p-3 border border-[var(--color-border)]">
        <button
          onClick={goToPrevMonth}
          className="p-2 hover:bg-[var(--color-bg-tertiary)] rounded-lg transition-colors"
        >
          <svg className="w-5 h-5 text-[var(--color-text-secondary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        
        <div className="text-center">
          <button
            onClick={goToToday}
            className="text-lg font-semibold text-[var(--color-text-primary)] hover:text-[var(--color-accent)] transition-colors"
          >
            {monthNames[month]} {year}
          </button>
        </div>
        
        <button
          onClick={goToNextMonth}
          className="p-2 hover:bg-[var(--color-bg-tertiary)] rounded-lg transition-colors"
        >
          <svg className="w-5 h-5 text-[var(--color-text-secondary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      
      {/* Legend */}
      <div className="flex flex-wrap gap-2 mb-4">
        {Object.entries(entryConfig).map(([type, config]) => (
          <div key={type} className="flex items-center gap-1.5 text-xs">
            <div className={`w-2 h-2 rounded-full ${config.dotColor}`}></div>
            <span className="text-[var(--color-text-muted)]">{t(`calendar.types.${type}`)}</span>
          </div>
        ))}
      </div>
      
      {/* Calendar Grid */}
      <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden">
        {/* Day Headers */}
        <div className="grid grid-cols-7 border-b border-[var(--color-border)]">
          {dayNames.map((day, index) => (
            <div
              key={index}
              className="py-2 text-center text-xs font-medium text-[var(--color-text-muted)]"
            >
              {day}
            </div>
          ))}
        </div>
        
        {/* Calendar Days */}
        <div className="grid grid-cols-7">
          {loading ? (
            <SkeletonScreen className="col-span-7 grid grid-cols-7">
              {Array.from({ length: 42 }).map((_, i) => (
                <div key={i} className="aspect-square border border-[var(--color-border)] p-1">
                  <Skeleton className="h-4 w-4 rounded" />
                </div>
              ))}
            </SkeletonScreen>
          ) : (
            calendarDays.map((dayInfo, index) => {
              const entryTypes = getEntryTypesForDate(dayInfo.date)
              const hasEntries = entryTypes.length > 0
              
              return (
                <button
                  key={index}
                  onClick={() => handleDayClick(dayInfo.date)}
                  className={`
                    relative min-h-[60px] p-1 border-b border-r border-[var(--color-border)]
                    transition-colors touch-manipulation
                    ${dayInfo.isCurrentMonth ? 'bg-transparent' : 'bg-[var(--color-bg-secondary)]'}
                    ${dayInfo.isToday ? 'bg-[var(--color-accent)]/10' : ''}
                    ${hasEntries ? 'hover:bg-[var(--color-bg-tertiary)]' : ''}
                    active:bg-[var(--color-bg-tertiary)]
                  `}
                >
                  <span
                    className={`
                      text-sm font-medium
                      ${dayInfo.isCurrentMonth ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'}
                      ${dayInfo.isToday ? 'bg-[var(--color-accent)] text-white w-6 h-6 rounded-full flex items-center justify-center mx-auto' : ''}
                    `}
                  >
                    {dayInfo.day}
                  </span>
                  
                  {/* Entry dots */}
                  {hasEntries && (
                    <div className="flex justify-center gap-0.5 mt-1 flex-wrap">
                      {entryTypes.map((type, i) => (
                        <div
                          key={i}
                          className={`w-1.5 h-1.5 rounded-full ${entryConfig[type]?.dotColor || 'bg-gray-500'}`}
                        />
                      ))}
                    </div>
                  )}
                </button>
              )
            })
          )}
        </div>
      </div>
      
      {/* Entry Count Summary */}
      <div className="mt-4 p-3 bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)]">
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--color-text-muted)]">{t('calendar.entriesThisMonth')}</span>
          <span className="font-semibold text-[var(--color-text-primary)]">
            {entries.filter(e => {
              const entryDate = new Date(e.date)
              return entryDate.getMonth() === month && entryDate.getFullYear() === year
            }).length}
          </span>
        </div>
      </div>
      
      {/* Day Detail Modal */}
      {showDayModal && selectedDate && (
        <div 
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50"
          onClick={() => setShowDayModal(false)}
        >
          <div 
            className="w-full max-w-lg bg-[var(--color-bg-secondary)] rounded-t-2xl max-h-[80vh] overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="sticky top-0 bg-[var(--color-bg-secondary)] px-4 py-3 border-b border-[var(--color-border)]">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                    {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-GB', { 
                      weekday: 'long', 
                      year: 'numeric', 
                      month: 'long', 
                      day: 'numeric' 
                    })}
                  </h2>
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {selectedDateEntries.length} {t('calendar.entries')}
                  </p>
                </div>
                <button
                  onClick={() => setShowDayModal(false)}
                  className="p-2 hover:bg-[var(--color-bg-tertiary)] rounded-lg"
                >
                  <svg className="w-5 h-5 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              {/* Type Filter */}
              <div className="flex gap-2 mt-3 overflow-x-auto pb-1 scrollbar-hide">
                {entryTypes.map(type => (
                  <button
                    key={type.key}
                    onClick={() => setFilterType(type.key)}
                    className={`
                      px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors
                      ${filterType === type.key 
                        ? 'bg-[var(--color-accent)] text-white' 
                        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'}
                    `}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Entries List */}
            <div className="overflow-y-auto max-h-[60vh] p-4 space-y-3">
              {selectedDateEntries.length === 0 ? (
                <div className="text-center py-8">
                  <svg className="w-12 h-12 mx-auto text-[var(--color-text-muted)] mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                  </svg>
                  <p className="text-[var(--color-text-muted)]">{t('calendar.noEntries')}</p>
                </div>
              ) : (
                selectedDateEntries.map(entry => {
                  const config = entryConfig[entry.type] || entryConfig.fuel
                  return (
                    <div
                      key={entry.id}
                      onClick={() => {
                        if (entry.vehicle_id) {
                          navigate(`/vehicles/${entry.vehicle_id}/expenses?tab=${entry.type}`)
                        }
                      }}
                      className={`p-3 rounded-xl border ${config.color} transition-transform active:scale-[0.98] ${entry.vehicle_id ? 'cursor-pointer hover:brightness-110' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">
                          {config.icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="font-medium text-[var(--color-text-primary)] truncate">
                              {entry.title}
                            </h3>
                            {entry.cost > 0 && (
                              <span className="text-sm font-semibold text-[var(--color-text-primary)] whitespace-nowrap">
                                {entry.cost.toFixed(2)}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                            {t(`calendar.types.${entry.type}`)}
                            {entry.vehicle_name && ` • ${entry.vehicle_name}`}
                          </p>
                          {entry.status && (
                            <span className={`
                              inline-block mt-1.5 px-2 py-0.5 rounded-full text-xs font-medium
                              ${entry.status === 'completed' ? 'bg-green-500/20 text-green-400' : 
                                entry.status === 'overdue' ? 'bg-red-500/20 text-red-400' : 
                                'bg-yellow-500/20 text-yellow-400'}
                            `}>
                              {t(`common.${entry.status}`)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
