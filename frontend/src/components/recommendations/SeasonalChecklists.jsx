/**
 * SeasonalChecklists - Displays seasonal vehicle maintenance checklists
 * 
 * Features:
 * - Auto-detects current season and shows relevant checklists
 * - Progress tracking with visual indicators
 * - Collapsible cards for space efficiency
 * - Syncs with backend for persistence
 * - Supports offline-first PWA usage
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { predictionApi } from '../../services/api'

// SVG Icons
const Icons = {
  snowflake: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="2" x2="12" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/>
      <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/><line x1="19.07" y1="4.93" x2="4.93" y2="19.07"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  ),
  sun: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  ),
  car: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.8 1.1l-.8 1.63A6 6 0 0 0 2 12.42V16h2"/>
      <circle cx="6.5" cy="16.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>
    </svg>
  ),
  clipboard: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
      <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
      <path d="M9 14l2 2 4-4"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
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
  refresh: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/>
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
  x: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  info: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  ),
}

// Checklist configurations with icons and colors
const CHECKLIST_CONFIG = {
  winter: {
    icon: Icons.snowflake,
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
  },
  summer: {
    icon: Icons.sun,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
  },
  pre_purchase: {
    icon: Icons.car,
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
  },
  state_inspection: {
    icon: Icons.clipboard,
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
  },
}

// Single Checklist Item Component
function ChecklistItem({ item, checklistId, onToggle, t }) {
  const [isLoading, setIsLoading] = useState(false)
  
  const handleToggle = async () => {
    setIsLoading(true)
    try {
      await onToggle(checklistId, item.id, !item.completed)
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <button
      onClick={handleToggle}
      disabled={isLoading}
      className={`
        w-full flex items-center gap-3 p-3 rounded-lg transition-all duration-200
        ${item.completed 
          ? 'bg-green-500/10 text-[var(--color-text-secondary)]' 
          : 'bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)]'
        }
        ${isLoading ? 'opacity-50 cursor-wait' : 'cursor-pointer'}
        touch-manipulation
      `}
    >
      <div className={`
        w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 transition-all
        ${item.completed 
          ? 'bg-green-500 text-white' 
          : 'border-2 border-[var(--color-border)]'
        }
      `}>
        {item.completed && Icons.check}
      </div>
      <span className={`text-sm ${item.completed ? 'line-through opacity-60' : ''}`}>
        {t(`seasonalChecklists.items.${item.id}`) || item.id}
      </span>
    </button>
  )
}

// Single Checklist Card Component
function ChecklistCard({ checklist, onToggleItem, onReset, onDismiss, t, defaultExpanded = false }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [showActions, setShowActions] = useState(false)
  
  const config = CHECKLIST_CONFIG[checklist.id] || CHECKLIST_CONFIG.state_inspection
  const title = t(`seasonalChecklists.${checklist.id}.title`) || checklist.id
  const description = t(`seasonalChecklists.${checklist.id}.description`) || ''
  
  // Calculate progress
  const progressPercent = checklist.progress_percent || 0
  const isComplete = progressPercent === 100
  
  return (
    <div className={`
      rounded-xl border overflow-hidden transition-all duration-300
      ${config.bgColor} ${config.borderColor}
    `}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center gap-3 touch-manipulation"
      >
        <div className={`w-10 h-10 rounded-xl ${config.bgColor} flex items-center justify-center ${config.color}`}>
          {config.icon}
        </div>
        
        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold truncate">{title}</h3>
            {isComplete && (
              <span className="text-2xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 font-medium">
                {t('seasonalChecklists.complete')}
              </span>
            )}
            {checklist.is_seasonal && checklist.is_in_season && !isComplete && (
              <span className="text-2xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 font-medium">
                {t('seasonalChecklists.inSeason')}
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            {checklist.completed_count}/{checklist.total_count} {t('seasonalChecklists.itemsCompleted')}
          </p>
        </div>
        
        {/* Progress Circle */}
        <div className="relative w-10 h-10 flex-shrink-0">
          <svg className="w-10 h-10 transform -rotate-90">
            <circle
              cx="20"
              cy="20"
              r="16"
              fill="none"
              stroke="var(--color-border)"
              strokeWidth="3"
            />
            <circle
              cx="20"
              cy="20"
              r="16"
              fill="none"
              stroke={isComplete ? '#22c55e' : 'var(--color-accent)'}
              strokeWidth="3"
              strokeDasharray={`${progressPercent} 100`}
              strokeLinecap="round"
              className="transition-all duration-500"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-2xs font-semibold">
            {progressPercent}%
          </span>
        </div>
        
        <span className={`text-[var(--color-text-muted)] transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}>
          {Icons.chevronDown}
        </span>
      </button>
      
      {/* Expanded Content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-2">
          {description && (
            <p className="text-xs text-[var(--color-text-secondary)] mb-3 flex items-start gap-2">
              <span className="text-[var(--color-text-muted)] mt-0.5">{Icons.info}</span>
              {description}
            </p>
          )}
          
          {/* Checklist Items */}
          <div className="space-y-2">
            {checklist.items.map(item => (
              <ChecklistItem
                key={item.id}
                item={item}
                checklistId={checklist.id}
                onToggle={onToggleItem}
                t={t}
              />
            ))}
          </div>
          
          {/* Actions */}
          <div className="flex items-center justify-between pt-3 mt-3 border-t border-[var(--color-border)]">
            <button
              onClick={() => setShowActions(!showActions)}
              className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
            >
              {t('seasonalChecklists.moreActions')}
            </button>
            
            {showActions && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onReset(checklist.id)}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] rounded-lg transition-colors"
                >
                  {Icons.refresh}
                  {t('seasonalChecklists.reset')}
                </button>
                <button
                  onClick={() => onDismiss(checklist.id, true)}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-[var(--color-text-secondary)] hover:text-red-400 bg-[var(--color-bg-secondary)] hover:bg-red-500/10 rounded-lg transition-colors"
                >
                  {Icons.x}
                  {t('seasonalChecklists.hide')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Main Component
export default function SeasonalChecklists({ compact = false, showOnlyInSeason = true }) {
  const { t } = useTranslation()
  const [checklists, setChecklists] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showDismissed, setShowDismissed] = useState(false)
  
  // Fetch checklists from API
  const fetchChecklists = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const response = await predictionApi.getChecklists()
      setChecklists(response.data.checklists || [])
    } catch (err) {
      console.error('Failed to load checklists:', err)
      setError(t('seasonalChecklists.loadError'))
    } finally {
      setIsLoading(false)
    }
  }, [t])
  
  useEffect(() => {
    fetchChecklists()
  }, [fetchChecklists])
  
  // Toggle item completion
  const handleToggleItem = async (checklistId, itemId, completed) => {
    try {
      await predictionApi.toggleChecklistItem(checklistId, itemId, completed)
      
      // Optimistic update
      setChecklists(prev => prev.map(cl => {
        if (cl.id !== checklistId) return cl
        
        const newItems = cl.items.map(item => 
          item.id === itemId ? { ...item, completed } : item
        )
        const completedCount = newItems.filter(i => i.completed).length
        
        return {
          ...cl,
          items: newItems,
          completed_count: completedCount,
          progress_percent: Math.round((completedCount / cl.total_count) * 100)
        }
      }))
    } catch (err) {
      console.error('Failed to toggle item:', err)
      // Revert on error
      fetchChecklists()
    }
  }
  
  // Reset checklist
  const handleReset = async (checklistId) => {
    if (!confirm(t('seasonalChecklists.resetConfirm'))) return
    
    try {
      await predictionApi.resetChecklist(checklistId)
      fetchChecklists()
    } catch (err) {
      console.error('Failed to reset checklist:', err)
    }
  }
  
  // Dismiss/restore checklist
  const handleDismiss = async (checklistId, dismissed) => {
    try {
      await predictionApi.dismissChecklist(checklistId, dismissed)
      setChecklists(prev => prev.map(cl => 
        cl.id === checklistId ? { ...cl, dismissed } : cl
      ))
    } catch (err) {
      console.error('Failed to dismiss checklist:', err)
    }
  }
  
  // Filter checklists based on settings
  const visibleChecklists = checklists.filter(cl => {
    // Filter out dismissed unless showDismissed is true
    if (cl.dismissed && !showDismissed) return false
    
    // In compact mode or showOnlyInSeason, only show seasonal checklists that are in season
    if (showOnlyInSeason && cl.is_seasonal && !cl.is_in_season) return false
    
    return true
  })
  
  const dismissedCount = checklists.filter(cl => cl.dismissed).length
  
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map(i => (
          <div key={i} className="skeleton h-24 rounded-xl" />
        ))}
      </div>
    )
  }
  
  if (error) {
    return (
      <div className="card p-4 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={fetchChecklists}
          className="mt-2 text-sm text-[var(--color-accent)] hover:underline"
        >
          {t('common.tryAgain')}
        </button>
      </div>
    )
  }
  
  if (visibleChecklists.length === 0 && !showDismissed) {
    return (
      <div className="card p-6 text-center">
        <div className="w-12 h-12 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-3">
          <span className="text-green-500">{Icons.check}</span>
        </div>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {t('seasonalChecklists.noChecklists')}
        </p>
        {dismissedCount > 0 && (
          <button
            onClick={() => setShowDismissed(true)}
            className="mt-2 text-sm text-[var(--color-accent)] hover:underline"
          >
            {t('seasonalChecklists.showHidden')} ({dismissedCount})
          </button>
        )}
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-[var(--color-accent)]/10 flex items-center justify-center text-[var(--color-accent)]">
            {Icons.clipboard}
          </div>
          <div>
            <h2 className="text-sm font-semibold">{t('seasonalChecklists.title')}</h2>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('seasonalChecklists.subtitle')}
            </p>
          </div>
        </div>
        
        {dismissedCount > 0 && (
          <button
            onClick={() => setShowDismissed(!showDismissed)}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            {showDismissed ? t('seasonalChecklists.hideHidden') : `${t('seasonalChecklists.showHidden')} (${dismissedCount})`}
          </button>
        )}
      </div>
      
      {/* Checklists */}
      <div className="space-y-3">
        {visibleChecklists.map((checklist, index) => (
          <ChecklistCard
            key={checklist.id}
            checklist={checklist}
            onToggleItem={handleToggleItem}
            onReset={handleReset}
            onDismiss={handleDismiss}
            t={t}
            defaultExpanded={false}
          />
        ))}
      </div>
      
      {/* Restore hidden checklists */}
      {showDismissed && dismissedCount > 0 && (
        <div className="text-center pt-2">
          <p className="text-xs text-[var(--color-text-muted)] mb-2">
            {t('seasonalChecklists.hiddenInfo')}
          </p>
          <button
            onClick={() => {
              checklists.filter(cl => cl.dismissed).forEach(cl => handleDismiss(cl.id, false))
            }}
            className="text-xs text-[var(--color-accent)] hover:underline"
          >
            {t('seasonalChecklists.restoreAll')}
          </button>
        </div>
      )}
    </div>
  )
}
