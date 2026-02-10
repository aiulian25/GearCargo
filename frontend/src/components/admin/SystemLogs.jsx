import { useState, useEffect } from 'react'
import { adminApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

// Icons
const Icons = {
  search: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  filter: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  x: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  chevronLeft: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  chevronRight: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  chevronDown: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  chevronUp: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15"/>
    </svg>
  ),
  globe: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  ),
  monitor: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
    </svg>
  ),
  smartphone: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
    </svg>
  ),
  tablet: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
    </svg>
  ),
  user: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  ),
  shield: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  activity: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
  alertTriangle: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  refresh: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
}

// Event type labels and colors
const eventTypeConfig = {
  login_success: { label: 'Login', color: 'text-green-500', bg: 'bg-green-500/10' },
  login_failed: { label: 'Login Failed', color: 'text-red-500', bg: 'bg-red-500/10' },
  login_blocked: { label: 'Login Blocked', color: 'text-orange-500', bg: 'bg-orange-500/10' },
  logout: { label: 'Logout', color: 'text-blue-500', bg: 'bg-blue-500/10' },
  registration: { label: 'Registration', color: 'text-purple-500', bg: 'bg-purple-500/10' },
  password_change: { label: 'Password Change', color: 'text-amber-500', bg: 'bg-amber-500/10' },
  '2fa_enabled': { label: '2FA Enabled', color: 'text-green-500', bg: 'bg-green-500/10' },
  '2fa_disabled': { label: '2FA Disabled', color: 'text-orange-500', bg: 'bg-orange-500/10' },
  '2fa_failed': { label: '2FA Failed', color: 'text-red-500', bg: 'bg-red-500/10' },
}

// Device type icon mapping
const deviceIcons = {
  desktop: Icons.monitor,
  mobile: Icons.smartphone,
  tablet: Icons.tablet,
}

export default function SystemLogs() {
  const { t } = useTranslation()
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [showFilters, setShowFilters] = useState(false)
  const [expandedLog, setExpandedLog] = useState(null)
  
  // Filter states
  const [eventType, setEventType] = useState('')
  const [category, setCategory] = useState('')
  const [successFilter, setSuccessFilter] = useState('')
  const [country, setCountry] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  
  useEffect(() => {
    fetchLogs()
  }, [currentPage, eventType, category, successFilter, country, startDate, endDate])
  
  const fetchLogs = async () => {
    setIsLoading(true)
    try {
      const response = await adminApi.getLogs({
        page: currentPage,
        perPage: 20,
        search: search || undefined,
        eventType: eventType || undefined,
        category: category || undefined,
        success: successFilter !== '' ? successFilter : undefined,
        country: country || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      })
      setLogs(response.data.logs)
      setTotalPages(response.data.pages)
      setFilters(response.data.filters)
      setStats(response.data.stats)
    } catch (error) {
      console.error('Failed to fetch logs:', error)
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleSearch = (e) => {
    e.preventDefault()
    setCurrentPage(1)
    fetchLogs()
  }
  
  const clearFilters = () => {
    setEventType('')
    setCategory('')
    setSuccessFilter('')
    setCountry('')
    setStartDate('')
    setEndDate('')
    setSearch('')
    setCurrentPage(1)
  }
  
  const formatDate = (dateString) => {
    if (!dateString) return '-'
    const date = new Date(dateString)
    return date.toLocaleString()
  }
  
  const getEventConfig = (type) => {
    return eventTypeConfig[type] || { label: type, color: 'text-gray-500', bg: 'bg-gray-500/10' }
  }
  
  const hasActiveFilters = eventType || category || successFilter !== '' || country || startDate || endDate || search
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[var(--color-accent)]">{Icons.activity}</span>
        <div>
          <h3 className="text-sm font-medium">{t('admin.systemLogs') || 'System Logs'}</h3>
          <p className="text-2xs text-[var(--color-text-muted)]">
            {t('admin.systemLogsDesc') || 'View login activity and security events'}
          </p>
        </div>
      </div>
      
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <p className="text-lg font-semibold">{stats.total_logs?.toLocaleString() || 0}</p>
            <p className="text-2xs text-[var(--color-text-muted)]">{t('admin.totalLogs') || 'Total'}</p>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <p className="text-lg font-semibold text-green-500">{stats.today_logs || 0}</p>
            <p className="text-2xs text-[var(--color-text-muted)]">{t('admin.todayLogs') || 'Today'}</p>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <p className="text-lg font-semibold text-red-500">{stats.failed_logins_today || 0}</p>
            <p className="text-2xs text-[var(--color-text-muted)]">{t('admin.failedToday') || 'Failed Today'}</p>
          </div>
        </div>
      )}
      
      {/* Search and Filter Bar */}
      <div className="flex gap-2 mb-4">
        <form onSubmit={handleSearch} className="flex-1">
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]">
              {Icons.search}
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('admin.searchLogs') || 'Search by IP, description, location...'}
              className="w-full pl-10 pr-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] text-sm border border-transparent focus:border-[var(--color-accent)] focus:outline-none"
            />
          </div>
        </form>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
            hasActiveFilters 
              ? 'bg-[var(--color-accent)] text-white' 
              : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
          }`}
        >
          {Icons.filter}
          <span className="text-sm">{t('common.filter') || 'Filter'}</span>
          {showFilters ? Icons.chevronUp : Icons.chevronDown}
        </button>
        <button
          onClick={fetchLogs}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]/80 transition-colors"
          title={t('common.refresh') || 'Refresh'}
        >
          {Icons.refresh}
        </button>
      </div>
      
      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {/* Event Type */}
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.eventType') || 'Event Type'}
              </label>
              <select
                value={eventType}
                onChange={(e) => { setEventType(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              >
                <option value="">{t('common.all') || 'All'}</option>
                {filters?.event_types?.map(type => (
                  <option key={type} value={type}>
                    {getEventConfig(type).label}
                  </option>
                ))}
              </select>
            </div>
            
            {/* Success/Failed */}
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.status') || 'Status'}
              </label>
              <select
                value={successFilter}
                onChange={(e) => { setSuccessFilter(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              >
                <option value="">{t('common.all') || 'All'}</option>
                <option value="true">{t('common.success') || 'Success'}</option>
                <option value="false">{t('common.failed') || 'Failed'}</option>
              </select>
            </div>
            
            {/* Country */}
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.country') || 'Country'}
              </label>
              <select
                value={country}
                onChange={(e) => { setCountry(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              >
                <option value="">{t('common.all') || 'All'}</option>
                {filters?.countries?.map(c => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
            </div>
            
            {/* Category */}
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.category') || 'Category'}
              </label>
              <select
                value={category}
                onChange={(e) => { setCategory(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              >
                <option value="">{t('common.all') || 'All'}</option>
                {filters?.categories?.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            
            {/* Date Range */}
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.startDate') || 'Start Date'}
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => { setStartDate(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              />
            </div>
            <div>
              <label className="block text-2xs text-[var(--color-text-muted)] mb-1">
                {t('admin.endDate') || 'End Date'}
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => { setEndDate(e.target.value); setCurrentPage(1) }}
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] text-sm border border-[var(--color-border)]"
              />
            </div>
          </div>
          
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-sm text-[var(--color-accent)] hover:underline"
            >
              {t('common.clearFilters') || 'Clear all filters'}
            </button>
          )}
        </div>
      )}
      
      {/* Logs List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
        </div>
      ) : logs.length === 0 ? (
        <div className="text-center py-8 text-[var(--color-text-muted)]">
          <div className="mb-2">{Icons.activity}</div>
          <p className="text-sm">{t('admin.noLogs') || 'No activity logs found'}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {logs.map((log) => {
            const config = getEventConfig(log.event_type)
            const isExpanded = expandedLog === log.id
            
            return (
              <div
                key={log.id}
                className="bg-[var(--color-bg-tertiary)] rounded-lg overflow-hidden"
              >
                {/* Main row */}
                <div
                  onClick={() => setExpandedLog(isExpanded ? null : log.id)}
                  className="flex items-center gap-3 p-3 cursor-pointer hover:bg-[var(--color-bg-tertiary)]/80"
                >
                  {/* Event badge */}
                  <div className={`px-2 py-1 rounded-md text-2xs font-medium ${config.bg} ${config.color}`}>
                    {config.label}
                  </div>
                  
                  {/* User info */}
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    {log.user_email ? (
                      <>
                        <span className="text-[var(--color-text-muted)]">{Icons.user}</span>
                        <span className="text-sm truncate">{log.user_email}</span>
                      </>
                    ) : (
                      <span className="text-sm text-[var(--color-text-muted)]">
                        {t('admin.anonymous') || 'Anonymous'}
                      </span>
                    )}
                  </div>
                  
                  {/* Location */}
                  {(log.city || log.country) && (
                    <div className="hidden sm:flex items-center gap-1 text-[var(--color-text-muted)]">
                      {Icons.globe}
                      <span className="text-2xs">
                        {[log.city, log.country_code].filter(Boolean).join(', ')}
                      </span>
                    </div>
                  )}
                  
                  {/* Device */}
                  <div className="hidden sm:flex items-center text-[var(--color-text-muted)]">
                    {deviceIcons[log.device_type] || Icons.monitor}
                  </div>
                  
                  {/* Status indicator */}
                  <div className={`w-2 h-2 rounded-full ${log.success ? 'bg-green-500' : 'bg-red-500'}`} />
                  
                  {/* Time */}
                  <span className="text-2xs text-[var(--color-text-muted)] whitespace-nowrap">
                    {formatDate(log.created_at)}
                  </span>
                  
                  {/* Expand icon */}
                  <span className="text-[var(--color-text-muted)]">
                    {isExpanded ? Icons.chevronUp : Icons.chevronDown}
                  </span>
                </div>
                
                {/* Expanded details */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-2 border-t border-[var(--color-border)] space-y-3">
                    {/* Description */}
                    {log.description && (
                      <p className="text-sm text-[var(--color-text-secondary)]">{log.description}</p>
                    )}
                    
                    {/* Error message */}
                    {log.error_message && (
                      <div className="flex items-center gap-2 text-red-500 text-sm">
                        {Icons.alertTriangle}
                        <span>{log.error_message}</span>
                      </div>
                    )}
                    
                    {/* Details grid */}
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.ipAddress') || 'IP Address'}
                        </span>
                        <p className="font-mono">{log.ip_address || '-'}</p>
                      </div>
                      
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.device') || 'Device'}
                        </span>
                        <p className="capitalize">{log.device_type || '-'}</p>
                      </div>
                      
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.browser') || 'Browser'}
                        </span>
                        <p>{log.browser ? `${log.browser} ${log.browser_version || ''}` : '-'}</p>
                      </div>
                      
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.os') || 'OS'}
                        </span>
                        <p>{log.os ? `${log.os} ${log.os_version || ''}` : '-'}</p>
                      </div>
                      
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.location') || 'Location'}
                        </span>
                        <p>{[log.city, log.region, log.country].filter(Boolean).join(', ') || '-'}</p>
                      </div>
                      
                      <div>
                        <span className="text-2xs text-[var(--color-text-muted)]">
                          {t('admin.language') || 'Language'}
                        </span>
                        <p>{log.device_language || '-'}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      
      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 pt-4">
          <button
            onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
            disabled={currentPage === 1}
            className="p-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {Icons.chevronLeft}
          </button>
          <span className="text-sm text-[var(--color-text-secondary)]">
            {t('common.page') || 'Page'} {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
            disabled={currentPage === totalPages}
            className="p-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {Icons.chevronRight}
          </button>
        </div>
      )}
    </div>
  )
}
