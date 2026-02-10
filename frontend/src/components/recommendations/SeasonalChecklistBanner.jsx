/**
 * SeasonalChecklistBanner - A compact, dismissible banner for the Dashboard
 * 
 * Shows a quick tip when seasonal checklists are relevant.
 * Non-intrusive, links to the full SmartRecommendations page.
 */
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { predictionApi } from '../../services/api'

// SVG Icons
const Icons = {
  snowflake: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="2" x2="12" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/>
      <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/><line x1="19.07" y1="4.93" x2="4.93" y2="19.07"/>
    </svg>
  ),
  sun: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
    </svg>
  ),
  x: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  chevronRight: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
}

export default function SeasonalChecklistBanner() {
  const { t } = useTranslation()
  const [bannerData, setBannerData] = useState(null)
  const [isDismissed, setIsDismissed] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  
  // Check localStorage for dismissal state
  useEffect(() => {
    const dismissedUntil = localStorage.getItem('seasonalBannerDismissed')
    if (dismissedUntil) {
      const dismissDate = new Date(dismissedUntil)
      if (dismissDate > new Date()) {
        setIsDismissed(true)
      } else {
        localStorage.removeItem('seasonalBannerDismissed')
      }
    }
  }, [])
  
  // Fetch checklist data
  useEffect(() => {
    if (isDismissed) {
      setIsLoading(false)
      return
    }
    
    const fetchData = async () => {
      try {
        const response = await predictionApi.getChecklists()
        const checklists = response.data.checklists || []
        
        // Find a relevant seasonal checklist that's in season and not complete
        const relevantChecklist = checklists.find(cl => 
          cl.is_seasonal && 
          cl.is_in_season && 
          !cl.dismissed && 
          cl.progress_percent < 100
        )
        
        if (relevantChecklist) {
          setBannerData({
            id: relevantChecklist.id,
            progress: relevantChecklist.progress_percent,
            completed: relevantChecklist.completed_count,
            total: relevantChecklist.total_count,
          })
        }
      } catch (err) {
        console.error('Failed to load checklist banner data:', err)
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [isDismissed])
  
  // Dismiss handler - dismisses for 7 days
  const handleDismiss = (e) => {
    e.preventDefault()
    e.stopPropagation()
    const dismissUntil = new Date()
    dismissUntil.setDate(dismissUntil.getDate() + 7)
    localStorage.setItem('seasonalBannerDismissed', dismissUntil.toISOString())
    setIsDismissed(true)
  }
  
  // Don't show if dismissed, loading, or no relevant data
  if (isDismissed || isLoading || !bannerData) {
    return null
  }
  
  // Determine season icon and styling
  const isWinter = bannerData.id === 'winter'
  const icon = isWinter ? Icons.snowflake : Icons.sun
  const bgClass = isWinter 
    ? 'bg-gradient-to-r from-blue-500/10 to-cyan-500/10 border-blue-500/30' 
    : 'bg-gradient-to-r from-amber-500/10 to-orange-500/10 border-amber-500/30'
  const iconColor = isWinter ? 'text-blue-400' : 'text-amber-400'
  
  const title = t(`seasonalChecklists.${bannerData.id}.title`)
  
  return (
    <Link
      to="/recommendations"
      className={`
        block rounded-xl border p-3 transition-all duration-200
        hover:shadow-md hover:scale-[1.01] touch-manipulation
        ${bgClass}
      `}
    >
      <div className="flex items-center gap-3">
        {/* Icon */}
        <div className={`flex-shrink-0 ${iconColor}`}>
          {icon}
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{title}</span>
            <span className="text-2xs px-1.5 py-0.5 rounded-full bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]">
              {bannerData.progress}%
            </span>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            {t('seasonalChecklists.bannerTip')} • {bannerData.completed}/{bannerData.total} {t('seasonalChecklists.itemsCompleted')}
          </p>
        </div>
        
        {/* Arrow */}
        <div className="flex-shrink-0 text-[var(--color-text-muted)]">
          {Icons.chevronRight}
        </div>
        
        {/* Dismiss button */}
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 p-1.5 rounded-lg hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          aria-label="Dismiss"
        >
          {Icons.x}
        </button>
      </div>
    </Link>
  )
}
