import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { formatDateShort, formatMonthYear } from '../../utils/dateFormat'

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
  tools: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h4L17.5 10.5a2.121 2.121 0 0 0-3-3L4 18v3z"/><path d="M14.5 5.5l4 4"/>
      <path d="M12 8L7 3 3 7l5 5"/>
    </svg>
  ),
  bell: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  checkSquare: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
  insurance: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  filter: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
    </svg>
  ),
  calendar: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
  edit: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
}

// Entry type configurations
const entryTypes = {
  fuel: { 
    icon: Icons.fuel, 
    color: 'text-amber-500', 
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500',
    editPath: 'fuel'
  },
  service: { 
    icon: Icons.wrench, 
    color: 'text-blue-500', 
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500',
    editPath: 'service'
  },
  tax: { 
    icon: Icons.receipt, 
    color: 'text-rose-500', 
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-rose-500',
    editPath: 'tax'
  },
  parking: { 
    icon: Icons.parking, 
    color: 'text-purple-500', 
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500',
    editPath: 'parking'
  },
  repair: { 
    icon: Icons.tools, 
    color: 'text-red-500', 
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500',
    editPath: 'repair'
  },
  reminder: { 
    icon: Icons.bell, 
    color: 'text-green-500', 
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500',
    editPath: 'reminder'
  },
  todo: { 
    icon: Icons.checkSquare, 
    color: 'text-indigo-500', 
    bgColor: 'bg-indigo-500/10',
    borderColor: 'border-indigo-500',
    editPath: 'todo'
  },
  insurance: { 
    icon: Icons.insurance, 
    color: 'text-teal-500', 
    bgColor: 'bg-teal-500/10',
    borderColor: 'border-teal-500',
    editPath: 'insurance'
  },
}

export default function VehicleTimeline() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  
  const [vehicle, setVehicle] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [filteredTimeline, setFilteredTimeline] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [showFilters, setShowFilters] = useState(false)
  
  const filterOptions = [
    { id: 'all', label: t('timeline.all') || 'All' },
    { id: 'fuel', label: t('timeline.fuel') || 'Fuel' },
    { id: 'service', label: t('timeline.service') || 'Service' },
    { id: 'repair', label: t('timeline.repair') || 'Repair' },
    { id: 'tax', label: t('timeline.tax') || 'Tax' },
    { id: 'parking', label: t('timeline.parking') || 'Parking' },
    { id: 'reminder', label: t('timeline.reminder') || 'Reminder' },
    { id: 'todo', label: t('timeline.todo') || 'Todo' },
    { id: 'insurance', label: t('timeline.insurance') || 'Insurance' },
  ]
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [vehicleRes, timelineRes] = await Promise.all([
          vehicleApi.getById(id),
          vehicleApi.getTimeline(id)
        ])
        setVehicle(vehicleRes.data)
        const entries = timelineRes.data?.entries || []
        setTimeline(entries)
        setFilteredTimeline(entries)
      } catch (error) {
        console.error('Failed to fetch timeline:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [id, navigate])
  
  useEffect(() => {
    if (filter === 'all') {
      setFilteredTimeline(timeline)
    } else {
      setFilteredTimeline(timeline.filter(entry => entry.type === filter))
    }
  }, [filter, timeline])
  
  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return `${currency.symbol}0`
    return `${currency.symbol}${Number(amount).toFixed(2)}`
  }
  
  const formatDate = (dateStr) => formatDateShort(dateStr)
  
  const getEntryStyle = (type) => {
    return entryTypes[type] || { 
      icon: Icons.calendar, 
      color: 'text-gray-500', 
      bgColor: 'bg-gray-500/10',
      borderColor: 'border-gray-500',
      editPath: null
    }
  }
  
  const getEditUrl = (entry) => {
    const style = getEntryStyle(entry.type)
    if (!style.editPath || !entry.id) return null
    return `/vehicles/${id}/${style.editPath}/add?edit=${entry.id}`
  }
  
  // Group timeline by month
  const groupByMonth = (entries) => {
    const groups = {}
    entries.forEach(entry => {
      const date = new Date(entry.date)
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = formatMonthYear(date)
      if (!groups[key]) {
        groups[key] = { label, entries: [] }
      }
      groups[key].entries.push(entry)
    })
    // Sort by key descending (newest first)
    return Object.entries(groups)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([key, value]) => value)
  }
  
  const groupedTimeline = groupByMonth(filteredTimeline)
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-14 rounded-xl mb-4" />
        <div className="skeleton h-12 rounded-xl mb-4" />
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
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
              <h1 className="text-lg font-semibold">{t('timeline.title') || 'Timeline'}</h1>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {vehicle?.make} {vehicle?.model} • {filteredTimeline.length} {t('timeline.entries') || 'entries'}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-2 rounded-lg transition-colors ${
              showFilters || filter !== 'all' 
                ? 'bg-[var(--color-accent)] text-white' 
                : 'hover:bg-[var(--color-bg-tertiary)]'
            }`}
          >
            {Icons.filter}
          </button>
        </div>
        
        {/* Filter pills */}
        {showFilters && (
          <div className="px-4 pb-4 overflow-x-auto">
            <div className="flex gap-2">
              {filterOptions.map(option => (
                <button
                  key={option.id}
                  onClick={() => setFilter(option.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                    filter === option.id
                      ? 'bg-[var(--color-accent)] text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      
      {/* Timeline content */}
      <div className="p-4">
        {groupedTimeline.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--color-bg-tertiary)] flex items-center justify-center">
              {Icons.calendar}
            </div>
            <h3 className="font-medium mb-1">{t('timeline.noEntries') || 'No entries found'}</h3>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {filter !== 'all' 
                ? t('timeline.noEntriesFilter') || 'Try changing the filter'
                : t('timeline.noEntriesYet') || 'Start adding expenses to see them here'}
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {groupedTimeline.map((group, groupIdx) => (
              <div key={groupIdx}>
                {/* Month header */}
                <div className="sticky top-[72px] z-[5] bg-[var(--color-bg-primary)] py-2 mb-3">
                  <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">
                    {group.label}
                  </h2>
                </div>
                
                {/* Timeline entries */}
                <div className="relative">
                  {/* Vertical line */}
                  <div className="absolute left-[15px] top-0 bottom-0 w-0.5 bg-[var(--color-border)]" />
                  
                  <div className="space-y-4">
                    {group.entries.map((entry, idx) => {
                      const style = getEntryStyle(entry.type)
                      const editUrl = getEditUrl(entry)
                      
                      return (
                        <div key={idx} className="relative pl-10">
                          {/* Timeline dot */}
                          <div className={`absolute left-0 top-3 w-8 h-8 rounded-full ${style.bgColor} flex items-center justify-center ${style.color} z-[1]`}>
                            {style.icon}
                          </div>
                          
                          {/* Entry card */}
                          <div className={`bg-[var(--color-bg-secondary)] rounded-xl p-4 border-l-4 ${style.borderColor}`}>
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div className="flex-1 min-w-0">
                                <span className={`inline-block px-2 py-0.5 rounded-full text-2xs font-medium ${style.bgColor} ${style.color} mb-1`}>
                                  {t(`timeline.${entry.type}`) || entry.type.charAt(0).toUpperCase() + entry.type.slice(1)}
                                </span>
                                <h3 className="font-medium truncate">
                                  {entry.description || entry.title || '-'}
                                </h3>
                              </div>
                              {entry.cost !== undefined && entry.cost !== null && (
                                <span className="font-semibold text-[var(--color-text-primary)] whitespace-nowrap">
                                  {formatCurrency(entry.cost)}
                                </span>
                              )}
                            </div>
                            
                            <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
                              <span>{formatDate(entry.date)}</span>
                              {editUrl && (
                                <Link
                                  to={editUrl}
                                  className={`flex items-center gap-1 ${style.color} hover:underline`}
                                >
                                  {Icons.edit}
                                  <span>{t('common.edit') || 'Edit'}</span>
                                </Link>
                              )}
                            </div>
                            
                            {/* Additional details */}
                            {entry.mileage && (
                              <div className="mt-2 pt-2 border-t border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]">
                                {t('timeline.mileage') || 'Mileage'}: {entry.mileage.toLocaleString()} km
                              </div>
                            )}
                            
                            {entry.notes && (
                              <div className="mt-2 pt-2 border-t border-[var(--color-border)] text-xs text-[var(--color-text-secondary)]">
                                {entry.notes}
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
