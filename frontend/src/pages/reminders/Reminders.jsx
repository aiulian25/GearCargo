import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { reminderApi } from '../../services/api'
import { formatDistanceToNow, isPast, isToday, isTomorrow, parseISO } from 'date-fns'
import { useTranslation } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

export default function Reminders() {
  const { t } = useTranslation()
  const [reminders, setReminders] = useState([])
  const [filter, setFilter] = useState('upcoming')
  const [isLoading, setIsLoading] = useState(true)
  const [stats, setStats] = useState(null)
  const [snoozingId, setSnoozingId] = useState(null)
  
  // Load stats once on mount
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await reminderApi.getStats()
        setStats(response.data)
      } catch (error) {
        console.error('Failed to fetch reminder stats:', error)
      }
    }
    fetchStats()
  }, [])
  
  useEffect(() => {
    const fetchReminders = async () => {
      setIsLoading(true)
      try {
        const response = await reminderApi.getAll({ status: filter })
        setReminders(response.data.reminders || [])
      } catch (error) {
        console.error('Failed to fetch reminders:', error)
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchReminders()
  }, [filter])
  
  const handleComplete = async (id, e) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    
    try {
      await reminderApi.complete(id)
      setReminders(reminders.filter(r => r.id !== id))
      // Refresh stats
      const statsResponse = await reminderApi.getStats()
      setStats(statsResponse.data)
    } catch (error) {
      console.error('Failed to complete reminder:', error)
    }
  }
  
  const handleSnooze = async (id, days, e) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    
    setSnoozingId(id)
    try {
      await reminderApi.snooze(id, days)
      toast.success(t('reminders.snoozedSuccess') || `Reminder snoozed for ${days} days`)
      // Refresh list
      const response = await reminderApi.getAll({ status: filter })
      setReminders(response.data.reminders || [])
    } catch (error) {
      console.error('Failed to snooze reminder:', error)
      toast.error(t('reminders.snoozeFailed') || 'Failed to snooze reminder')
    } finally {
      setSnoozingId(null)
    }
  }
  
  const getDueDateLabel = (dateStr) => {
    const date = parseISO(dateStr)
    
    if (isPast(date) && !isToday(date)) {
      return { text: t('reminders.overdue'), className: 'text-red-500' }
    }
    if (isToday(date)) {
      return { text: t('common.today'), className: 'text-amber-500' }
    }
    if (isTomorrow(date)) {
      return { text: t('common.tomorrow'), className: 'text-blue-500' }
    }
    
    return { 
      text: formatDistanceToNow(date, { addSuffix: true }),
      className: 'text-[var(--color-text-muted)]'
    }
  }
  
  const getTypeIcon = (type) => {
    const icons = {
      service: 'build',
      insurance: 'shield',
      tax: 'receipt_long',
      inspection: 'fact_check',
      oil_change: 'oil_barrel',
      tire_rotation: 'tire_repair',
      custom: 'notifications',
    }
    return icons[type] || 'notifications'
  }
  
  const filters = [
    { id: 'upcoming', label: t('reminders.upcoming') },
    { id: 'overdue', label: t('reminders.overdue') },
    { id: 'completed', label: t('reminders.completed') },
  ]
  
  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold">{t('reminders.title')}</h1>
        <Link to="/reminders/add" className="btn btn-primary btn-sm">
          <span className="material-icons-outlined icon-sm">add</span>
          {t('reminders.add')}
        </Link>
      </div>
      
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-[var(--color-accent)]">{stats.total || 0}</div>
            <div className="text-2xs text-[var(--color-text-muted)]">{t('reminders.statsTotal') || 'Total'}</div>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-blue-500">{stats.pending || 0}</div>
            <div className="text-2xs text-[var(--color-text-muted)]">{t('reminders.statsPending') || 'Pending'}</div>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <div className={`text-lg font-bold ${stats.overdue > 0 ? 'text-red-500' : 'text-[var(--color-text-secondary)]'}`}>{stats.overdue || 0}</div>
            <div className="text-2xs text-[var(--color-text-muted)]">{t('reminders.statsOverdue') || 'Overdue'}</div>
          </div>
          <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3 text-center">
            <div className="text-lg font-bold text-green-500">{stats.completed || 0}</div>
            <div className="text-2xs text-[var(--color-text-muted)]">{t('reminders.statsCompleted') || 'Done'}</div>
          </div>
        </div>
      )}
      
      {/* Filters */}
      <div className="flex bg-[var(--color-bg-tertiary)] rounded-lg p-1 mb-4">
        {filters.map(f => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`flex-1 py-2 rounded-md text-xs font-medium transition-colors ${
              filter === f.id 
                ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm' 
                : 'text-[var(--color-text-secondary)]'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      
      {/* Reminders List */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="skeleton h-20 rounded-xl" />
          ))}
        </div>
      ) : reminders.length === 0 ? (
        <div className="card text-center py-12">
          <span className="material-icons-outlined icon-xl text-[var(--color-text-muted)] mb-3">
            {filter === 'completed' ? 'task_alt' : 'notifications_none'}
          </span>
          <h3 className="text-sm font-medium mb-1">
            {filter === 'completed' ? t('reminders.noCompletedReminders') : t('reminders.noReminders')}
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            {filter === 'upcoming' 
              ? t('reminders.addRemindersHint')
              : filter === 'overdue'
              ? t('reminders.nothingOverdue')
              : t('reminders.completedAppearHere')}
          </p>
          {filter !== 'completed' && (
            <Link to="/reminders/add" className="btn btn-primary">
              {t('reminders.addReminder')}
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {reminders.map(reminder => {
            const dueDate = getDueDateLabel(reminder.due_date)
            
            return (
              <Link
                key={reminder.id}
                to={`/reminders/${reminder.id}`}
                className="card flex items-start gap-3 touch-manipulation"
              >
                {/* Icon */}
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  isPast(parseISO(reminder.due_date)) && !isToday(parseISO(reminder.due_date))
                    ? 'bg-red-500/10' 
                    : 'bg-[var(--color-accent)]/10'
                }`}>
                  <span className={`material-icons-outlined icon-sm ${
                    isPast(parseISO(reminder.due_date)) && !isToday(parseISO(reminder.due_date))
                      ? 'text-red-500' 
                      : 'text-[var(--color-accent)]'
                  }`}>
                    {getTypeIcon(reminder.type)}
                  </span>
                </div>
                
                {/* Content */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-medium truncate">{reminder.title}</h3>
                  <p className="text-2xs text-[var(--color-text-secondary)] truncate">
                    {reminder.vehicle_name || t('reminders.noVehicle') || 'No vehicle'}
                    {reminder.due_mileage && ` • ${reminder.due_mileage.toLocaleString()} ${reminder.vehicle_distance_unit || 'km'}`}
                  </p>
                  <p className={`text-2xs mt-0.5 ${dueDate.className}`}>
                    {dueDate.text}
                  </p>
                </div>
                
                {/* Actions */}
                {filter !== 'completed' && (
                  <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.preventDefault()}>
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleSnooze(reminder.id, 7, e); }}
                      className="btn-icon w-8 h-8"
                      disabled={snoozingId === reminder.id}
                      title={t('reminders.snooze7Days')}
                    >
                      {snoozingId === reminder.id ? (
                        <span className="material-icons-outlined icon-xs animate-spin">sync</span>
                      ) : (
                        <span className="material-icons-outlined icon-xs">snooze</span>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleComplete(reminder.id, e); }}
                      className="btn-icon w-8 h-8"
                      title={t('reminders.markComplete')}
                    >
                      <span className="material-icons-outlined icon-xs">check</span>
                    </button>
                  </div>
                )}
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
