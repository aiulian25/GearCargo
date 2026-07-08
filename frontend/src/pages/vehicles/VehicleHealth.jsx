import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { formatDate } from '../../utils/dateFormat'
import { formatFuelEconomy, resolveFuelSystem } from '../../utils/fuelEconomy'

// SVG Icons
const Icons = {
  arrowBack: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 19l-7-7 7-7"/>
    </svg>
  ),
  leaf: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>
    </svg>
  ),
  gauge: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z"/><path d="M12 14l3.5-3.5"/><circle cx="12" cy="14" r="1"/>
    </svg>
  ),
  wrench: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  fuel: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17"/><path d="M15 22H3"/><path d="M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3"/>
      <rect x="6" y="6" width="6" height="5" rx="1"/>
    </svg>
  ),
  tree: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22v-7"/><path d="M4 12h16"/><path d="m12 5 7 7-7-7-7 7 7-7Z"/>
      <path d="m6.5 17.5 5.5-5.5 5.5 5.5"/>
    </svg>
  ),
  warning: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  check: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  info: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
    </svg>
  ),
  clock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  trending: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
    </svg>
  ),
  wallet: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  chevronDown: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  chevronUp: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15"/>
    </svg>
  ),
}

// Health score ring component
const HealthScoreRing = ({ score, size = 120, strokeWidth = 10, label }) => {
  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (score / 100) * circumference
  
  const getColor = () => {
    if (score >= 80) return '#22c55e'
    if (score >= 60) return '#eab308'
    if (score >= 40) return '#f97316'
    return '#ef4444'
  }
  
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          className="text-[var(--color-bg-tertiary)]"
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        <circle
          className="transition-all duration-1000 ease-out"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          stroke={getColor()}
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-3xl font-bold">{score}</span>
        {label && <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>}
      </div>
    </div>
  )
}

// Progress bar component
const ProgressBar = ({ value, max = 100, color = 'bg-blue-500', showLabel = true, height = 'h-2' }) => {
  const percentage = Math.min(100, (value / max) * 100)
  
  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 ${height} bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden`}>
        <div
          className={`${height} ${color} rounded-full transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-medium w-10 text-right">{Math.round(percentage)}%</span>
      )}
    </div>
  )
}

// Component status badge
const StatusBadge = ({ status, t }) => {
  const styles = {
    good: 'bg-green-500/10 text-green-500 border-green-500/20',
    fair: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
    due_soon: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
    overdue: 'bg-red-500/10 text-red-500 border-red-500/20',
  }
  
  const getLabel = () => {
    switch (status) {
      case 'good': return t('vehicleHealth.statusGood') || 'Good'
      case 'fair': return t('vehicleHealth.statusFair') || 'Fair'
      case 'due_soon': return t('vehicleHealth.statusDueSoon') || 'Due Soon'
      case 'overdue': return t('vehicleHealth.statusOverdue') || 'Overdue'
      default: return status
    }
  }
  
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${styles[status] || styles.good}`}>
      {getLabel()}
    </span>
  )
}

// Expandable card component
const ExpandableCard = ({ title, icon, iconColor, children, defaultExpanded = false }) => {
  const [expanded, setExpanded] = useState(defaultExpanded)
  
  return (
    <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-[var(--color-bg-tertiary)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${iconColor}`}>
            {icon}
          </div>
          <span className="font-semibold">{title}</span>
        </div>
        {expanded ? Icons.chevronUp : Icons.chevronDown}
      </button>
      {expanded && (
        <div className="px-4 pb-4 border-t border-[var(--color-border)]">
          {children}
        </div>
      )}
    </div>
  )
}


export default function VehicleHealth() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  const { user } = useAuth()
  
  const [health, setHealth] = useState(null)
  const [warranties, setWarranties] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  // Mark Done state
  const [completingAction, setCompletingAction] = useState(null)
  const [completeForm, setCompleteForm] = useState({ mileage: '', notes: '' })
  const [completing, setCompleting] = useState(false)
  const [completeError, setCompleteError] = useState(null)
  const [completeSuccess, setCompleteSuccess] = useState(false)

  const fetchHealth = async () => {
    try {
      const response = await vehicleApi.getHealth(id)
      setHealth(response.data)
    } catch (err) {
      console.error('Failed to fetch health data:', err)
      setError(err.response?.data?.error || 'Failed to load health data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
  }, [id])

  // Warranty ledger — fetched independently so a failure never blocks health.
  useEffect(() => {
    let active = true
    vehicleApi.getWarranties(id)
      .then((res) => { if (active) setWarranties(res.data?.items || []) })
      .catch(() => { /* non-fatal: the warranty card just stays empty */ })
    return () => { active = false }
  }, [id])

  const handleMarkDone = (action) => {
    setCompletingAction(action)
    setCompleteForm({
      mileage: '',
      notes: '',
    })
    setCompleteError(null)
    setCompleteSuccess(false)
  }

  const handleCompleteSubmit = async () => {
    if (!completingAction) return
    setCompleting(true)
    setCompleteError(null)
    try {
      const payload = {
        component: completingAction.component,
      }
      if (completeForm.mileage !== '') {
        const mileageInt = parseInt(completeForm.mileage, 10)
        if (!isNaN(mileageInt) && mileageInt > 0) {
          payload.mileage = mileageInt
        }
      }
      if (completeForm.notes.trim()) {
        payload.notes = completeForm.notes.trim()
      }
      await vehicleApi.completeHealthAction(id, payload)
      setCompleteSuccess(true)
      setTimeout(() => {
        setCompletingAction(null)
        setCompleteSuccess(false)
        setIsLoading(true)
        fetchHealth()
      }, 1000)
    } catch (err) {
      setCompleteError(err.response?.data?.error || t('common.failed') || 'Failed. Please try again.')
    } finally {
      setCompleting(false)
    }
  }

  const handleCloseModal = () => {
    if (completing) return
    setCompletingAction(null)
    setCompleteError(null)
    setCompleteSuccess(false)
  }
  
  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return `${currency.symbol}0`
    return `${currency.symbol}${Number(amount).toFixed(2)}`
  }
  
  // Translate issue titles and descriptions from backend
  const translateIssue = (issue) => {
    const issueTranslations = {
      infrequent_service: {
        title: t('vehicleHealth.issue_infrequent_service_title') || 'Infrequent servicing',
        description: t('vehicleHealth.issue_infrequent_service_desc') || 'Recommended: at least yearly service.',
      },
      few_services: {
        title: t('vehicleHealth.issue_few_services_title') || 'Limited service history',
        description: t('vehicleHealth.issue_few_services_desc') || 'Consider documenting regular maintenance to maintain vehicle value.',
      },
      overdue_service: {
        title: t('vehicleHealth.issue_overdue_service_title') || 'Service overdue',
        description: t('vehicleHealth.issue_overdue_service_desc') || 'Schedule maintenance soon.',
      },
      service_due_soon: {
        title: t('vehicleHealth.issue_service_due_soon_title') || 'Service due soon',
        description: t('vehicleHealth.issue_service_due_soon_desc') || 'Plan your next service appointment.',
      },
      frequent_repairs: {
        title: t('vehicleHealth.issue_frequent_repairs_title') || 'Frequent repairs detected',
        description: t('vehicleHealth.issue_frequent_repairs_desc') || 'Consider a comprehensive inspection.',
      },
    }
    return issueTranslations[issue.id] || { title: issue.title, description: issue.description }
  }
  
  // Translate recommended action
  const translateAction = (action) => {
    // Component-based actions
    if (action.component) {
      const compName = t(`vehicleHealth.components_${action.component}`) || action.component.replace(/_/g, ' ')
      if (action.title.includes('Overdue')) {
        return {
          title: `${compName} - ${t('vehicleHealth.statusOverdue') || 'Overdue'}`,
          description: t('vehicleHealth.action_overdue_desc') || `Maintenance overdue. Recommended interval: ${action.description?.match(/\d+,?\d*/)?.[0] || ''} km.`,
        }
      }
      if (action.title.includes('Due Soon')) {
        return {
          title: `${compName} - ${t('vehicleHealth.statusDueSoon') || 'Due Soon'}`,
          description: action.description,
        }
      }
    }
    
    // Service-based actions
    if (action.type === 'service') {
      const translated = translateIssue({ id: action.title.toLowerCase().replace(/\s+/g, '_').replace('service_', '') })
      return translated.title !== action.title ? translated : { title: action.title, description: action.description }
    }
    
    // Environment actions
    if (action.type === 'environment') {
      return {
        title: t('vehicleHealth.action_carbon_offset_title') || 'Consider carbon offset',
        description: action.description,
      }
    }
    
    return { title: action.title, description: action.description }
  }
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-14 rounded-xl mb-4" />
        <div className="skeleton h-48 rounded-xl mb-4" />
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-20 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }
  
  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
          <p className="text-red-500">{error}</p>
          <button
            onClick={() => navigate(`/vehicles/${id}`)}
            className="mt-3 text-sm text-[var(--color-primary)] hover:underline"
          >
            {t('common.goBack') || 'Go Back'}
          </button>
        </div>
      </div>
    )
  }
  
  if (!health) return null

  const fuelEconomyUnit = health.vehicle_info?.distance_unit || user?.distance_unit || 'km'
  // F16: correct MPG gallon system for the user's region.
  const fuelSystem = resolveFuelSystem({ country: user?.country_preference, currency: user?.currency })
  const mpgLabel = t(fuelSystem === 'us' ? 'units.mpgUs' : 'units.mpgUk') || 'MPG'

  const getHealthStatusColor = () => {
    switch (health.health_status) {
      case 'excellent': return 'text-green-500'
      case 'good': return 'text-green-400'
      case 'fair': return 'text-yellow-500'
      default: return 'text-red-500'
    }
  }
  
  const getHealthStatusText = () => {
    switch (health.health_status) {
      case 'excellent': return t('vehicleHealth.statusExcellent') || 'Excellent'
      case 'good': return t('vehicleHealth.statusGood') || 'Good'
      case 'fair': return t('vehicleHealth.statusFair') || 'Fair'
      default: return t('vehicleHealth.statusNeedsAttention') || 'Needs Attention'
    }
  }
  
  // Sort monthly emissions for chart
  const emissionsData = Object.entries(health.carbon_footprint?.monthly_emissions || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-6)
  const maxEmission = Math.max(...emissionsData.map(([, v]) => v), 1)
  
  // Priority components to show
  const componentOrder = ['oil_change', 'brake_pads', 'tires', 'air_filter', 'battery', 'timing_belt']
  const priorityComponents = componentOrder
    .filter(key => health.components?.[key])
    .map(key => ({ key, ...health.components[key] }))
    .slice(0, 6)
  
  return (
    <div className="pb-20">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(`/vehicles/${id}`)} className="btn-icon">
            {Icons.arrowBack}
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold truncate">
              {t('vehicleHealth.pageTitle') || 'Vehicle Health'}
            </h1>
            <p className="text-xs text-[var(--color-text-secondary)]">{health.vehicle_name}</p>
          </div>
        </div>
      </div>
      
      <div className="p-4 space-y-4">
        {/* Overall Health Score */}
        <div className="bg-gradient-to-br from-[var(--color-bg-card)] to-[var(--color-bg-tertiary)] rounded-2xl border border-[var(--color-border)] p-6">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <h2 className="text-lg font-semibold mb-1">
                {t('vehicleHealth.overallHealth') || 'Overall Health'}
              </h2>
              <p className={`text-2xl font-bold ${getHealthStatusColor()}`}>
                {getHealthStatusText()}
              </p>
              <div className="mt-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[var(--color-text-secondary)]">
                    {t('vehicleHealth.maintenance') || 'Maintenance'}
                  </span>
                  <span className="font-medium">{health.scores?.maintenance || 0}%</span>
                </div>
                <ProgressBar value={health.scores?.maintenance || 0} color="bg-blue-500" showLabel={false} />
                
                <div className="flex items-center justify-between text-sm mt-2">
                  <span className="text-[var(--color-text-secondary)]">
                    {t('vehicleHealth.components') || 'Components'}
                  </span>
                  <span className="font-medium">{health.scores?.components || 0}%</span>
                </div>
                <ProgressBar value={health.scores?.components || 0} color="bg-green-500" showLabel={false} />
                
                <div className="flex items-center justify-between text-sm mt-2">
                  <span className="text-[var(--color-text-secondary)]">
                    {t('vehicleHealth.ecoDriving') || 'Eco-Driving'}
                  </span>
                  <span className="font-medium">{health.scores?.eco_driving || 0}%</span>
                </div>
                <ProgressBar value={health.scores?.eco_driving || 0} color="bg-emerald-500" showLabel={false} />
              </div>
            </div>
            <div className="ml-6">
              <HealthScoreRing 
                score={health.overall_score || 0} 
                label={t('vehicleHealth.score') || 'Score'}
              />
            </div>
          </div>
        </div>
        
        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)] mb-1">
              {Icons.leaf}
              <span className="text-xs">{t('vehicleHealth.yearlyCO2') || 'Yearly CO2'}</span>
            </div>
            <p className="text-xl font-bold">
              {health.carbon_footprint?.yearly_co2_kg?.toLocaleString() || 0} kg
            </p>
          </div>
          
          <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)] mb-1">
              {Icons.gauge}
              <span className="text-xs">{t('vehicleHealth.ecoScore') || 'Eco Score'}</span>
            </div>
            <p className="text-xl font-bold">
              {health.carbon_footprint?.eco_score || 0}/100
            </p>
          </div>
          
          <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)] mb-1">
              {Icons.fuel}
              <span className="text-xs">{t('vehicleHealth.avgEfficiency') || 'Avg Efficiency'}</span>
            </div>
            <p className="text-xl font-bold">
              {formatFuelEconomy(health.carbon_footprint?.avg_efficiency, fuelEconomyUnit, 1, { system: fuelSystem, mpgLabel })}
            </p>
          </div>
          
          <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] p-4">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)] mb-1">
              {Icons.wallet}
              <span className="text-xs">{t('vehicleHealth.costPerKm') || 'Cost/km'}</span>
            </div>
            <p className="text-xl font-bold">
              {health.cost_efficiency?.cost_per_km 
                ? `${currency.symbol}${health.cost_efficiency.cost_per_km.toFixed(2)}`
                : '-'
              }
            </p>
          </div>
        </div>
        
        {/* Recommended Actions */}
        {health.recommended_actions?.length > 0 && (
          <div className="bg-[var(--color-bg-card)] rounded-xl border border-[var(--color-border)] overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--color-border)] flex items-center gap-2">
              {Icons.warning}
              <h3 className="font-semibold">{t('vehicleHealth.recommendedActions') || 'Recommended Actions'}</h3>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {health.recommended_actions.slice(0, 5).map((action, idx) => {
                const translated = translateAction(action)
                const canMarkDone = action.type === 'maintenance' && action.component
                return (
                  <div key={idx} className="px-4 py-3 flex items-start gap-3">
                    <div className={`p-1.5 rounded-lg shrink-0 ${
                      action.priority === 'high' 
                        ? 'bg-red-500/10 text-red-500'
                        : action.priority === 'medium'
                          ? 'bg-orange-500/10 text-orange-500'
                          : 'bg-blue-500/10 text-blue-500'
                    }`}>
                      {action.priority === 'high' ? Icons.warning : 
                       action.priority === 'medium' ? Icons.clock : Icons.info}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm">{translated.title}</p>
                      <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">
                        {translated.description}
                      </p>
                    </div>
                    {canMarkDone && (
                      <button
                        onClick={() => handleMarkDone(action)}
                        className="shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border border-green-500/40 text-green-600 dark:text-green-400 bg-green-500/10 hover:bg-green-500/20 active:scale-95 transition-all touch-manipulation"
                        aria-label={`${t('vehicleHealth.markDone') || 'Mark as Done'}: ${translated.title}`}
                      >
                        {Icons.check}
                        <span className="hidden sm:inline">{t('vehicleHealth.markDone') || 'Done'}</span>
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
        
        {/* Carbon Footprint Section */}
        <ExpandableCard
          title={t('vehicleHealth.carbonFootprint') || 'Carbon Footprint'}
          icon={Icons.leaf}
          iconColor="bg-green-500/10 text-green-500"
          defaultExpanded={true}
        >
          <div className="pt-4 space-y-4">
            {/* CO2 Stats */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.totalCO2') || 'Total CO2'}
                </p>
                <p className="text-lg font-bold mt-1">
                  {(health.carbon_footprint?.total_co2_kg / 1000).toFixed(1)}t
                </p>
              </div>
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.ytdCO2') || 'YTD'}
                </p>
                <p className="text-lg font-bold mt-1">
                  {health.carbon_footprint?.ytd_co2_kg?.toLocaleString() || 0} kg
                </p>
              </div>
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">g/km</p>
                <p className="text-lg font-bold mt-1">
                  {health.carbon_footprint?.co2_per_km_grams || '-'}
                </p>
              </div>
            </div>
            
            {/* Emissions Chart */}
            {emissionsData.length > 0 && (
              <div>
                <p className="text-sm font-medium mb-3">
                  {t('vehicleHealth.monthlyEmissions') || 'Monthly Emissions (kg CO2)'}
                </p>
                <div className="space-y-2">
                  {emissionsData.map(([month, value]) => (
                    <div key={month} className="flex items-center gap-3">
                      <span className="text-xs text-[var(--color-text-secondary)] w-14">
                        {month.split('-')[1]}/{month.split('-')[0].slice(2)}
                      </span>
                      <div className="flex-1 h-5 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-green-500 rounded-full transition-all duration-500"
                          style={{ width: `${(value / maxEmission) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium w-12 text-right">
                        {value.toFixed(0)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Carbon Offset */}
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
              <div className="flex items-start gap-3">
                {Icons.tree}
                <div>
                  <p className="font-medium text-emerald-600 dark:text-emerald-400">
                    {t('vehicleHealth.carbonOffset') || 'Carbon Offset Recommendation'}
                  </p>
                  <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                    {t('vehicleHealth.treesNeeded') || 'Plant'} <strong>{Math.ceil(health.carbon_footprint?.trees_to_offset_yearly || 0)}</strong> {t('vehicleHealth.treesToOffset') || 'trees to offset yearly emissions'}
                  </p>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    {t('vehicleHealth.orOffset') || 'Or purchase carbon credits for'} <strong>~${health.carbon_footprint?.carbon_offset_cost_usd?.toFixed(0) || 0}</strong>/year
                  </p>
                </div>
              </div>
            </div>
          </div>
        </ExpandableCard>
        
        {/* Fuel Efficiency Tips */}
        {health.fuel_tips?.length > 0 && (
          <ExpandableCard
            title={t('vehicleHealth.fuelEfficiencyTips') || 'Fuel Efficiency Tips'}
            icon={Icons.fuel}
            iconColor="bg-amber-500/10 text-amber-500"
            defaultExpanded={true}
          >
            <div className="pt-4 space-y-3">
              {health.fuel_tips.map((tip, idx) => (
                <div 
                  key={idx}
                  className={`rounded-xl p-4 ${
                    tip.severity === 'success' 
                      ? 'bg-green-500/10 border border-green-500/20'
                      : 'bg-amber-500/10 border border-amber-500/20'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className={tip.severity === 'success' ? 'text-green-500' : 'text-amber-500'}>
                      {tip.severity === 'success' ? Icons.check : Icons.warning}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium">{tip.title}</p>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        {tip.description}
                      </p>
                      {tip.actions?.length > 0 && (
                        <ul className="mt-2 space-y-1">
                          {tip.actions.map((action, i) => (
                            <li key={i} className="text-sm flex items-center gap-2">
                              <span className="w-1 h-1 rounded-full bg-[var(--color-text-secondary)]" />
                              {action}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ExpandableCard>
        )}
        
        {/* Component Status */}
        <ExpandableCard
          title={t('vehicleHealth.componentStatus') || 'Component Status'}
          icon={Icons.wrench}
          iconColor="bg-blue-500/10 text-blue-500"
          defaultExpanded={false}
        >
          <div className="pt-4 space-y-3">
            {priorityComponents.map((comp) => (
              <div key={comp.key} className="flex items-center justify-between py-2 border-b border-[var(--color-border)] last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-sm">
                      {t(`vehicleHealth.components_${comp.key}`) || comp.key.replace(/_/g, ' ')}
                    </p>
                    <StatusBadge status={comp.status} t={t} />
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                    {comp.km_since_last?.toLocaleString() || 0} km / {comp.interval_km?.toLocaleString()} km {t('vehicleHealth.interval') || 'interval'}
                  </p>
                </div>
                <div className="w-24 ml-4">
                  <ProgressBar 
                    value={comp.wear_percentage} 
                    color={
                      comp.status === 'good' ? 'bg-green-500' :
                      comp.status === 'fair' ? 'bg-yellow-500' :
                      comp.status === 'due_soon' ? 'bg-orange-500' : 'bg-red-500'
                    }
                    showLabel={true}
                    height="h-1.5"
                  />
                </div>
              </div>
            ))}
            
            {Object.keys(health.components || {}).length > 6 && (
              <p className="text-xs text-[var(--color-text-secondary)] text-center pt-2">
                {t('vehicleHealth.showingTopComponents') || 'Showing top priority components'}
              </p>
            )}
          </div>
        </ExpandableCard>
        
        {/* Maintenance Status */}
        <ExpandableCard
          title={t('vehicleHealth.maintenanceStatus') || 'Maintenance Status'}
          icon={Icons.clock}
          iconColor="bg-indigo-500/10 text-indigo-500"
          defaultExpanded={false}
        >
          <div className="pt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.totalServices') || 'Total Services'}
                </p>
                <p className="text-xl font-bold mt-1">
                  {health.maintenance?.total_services || 0}
                </p>
              </div>
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.totalRepairs') || 'Total Repairs'}
                </p>
                <p className="text-xl font-bold mt-1">
                  {health.maintenance?.total_repairs || 0}
                </p>
              </div>
            </div>
            
            {health.maintenance?.last_service_date && (
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.lastService') || 'Last Service'}
                </span>
                <span className="text-sm font-medium">
                  {formatDate(health.maintenance.last_service_date)}
                  {health.maintenance.days_since_service > 0 && (
                    <span className="text-[var(--color-text-secondary)] ml-1">
                      ({health.maintenance.days_since_service}d ago)
                    </span>
                  )}
                </span>
              </div>
            )}
            
            {health.maintenance?.issues?.length > 0 && (
              <div className="space-y-2 mt-4">
                <p className="text-sm font-medium">{t('vehicleHealth.issues') || 'Issues'}</p>
                {health.maintenance.issues.map((issue, idx) => {
                  const translated = translateIssue(issue)
                  return (
                    <div 
                      key={idx}
                      className={`rounded-lg p-3 ${
                        issue.severity === 'error' ? 'bg-red-500/10' :
                        issue.severity === 'warning' ? 'bg-amber-500/10' : 'bg-blue-500/10'
                      }`}
                    >
                      <p className="text-sm font-medium">{translated.title}</p>
                      <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                        {translated.description}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </ExpandableCard>
        
        {/* Vehicle Info */}
        <ExpandableCard
          title={t('vehicleHealth.vehicleInfo') || 'Vehicle Info'}
          icon={Icons.shield}
          iconColor="bg-purple-500/10 text-purple-500"
          defaultExpanded={false}
        >
          <div className="pt-4 space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-[var(--color-border)]">
              <span className="text-sm text-[var(--color-text-secondary)]">
                {t('vehicleHealth.vehicleAge') || 'Vehicle Age'}
              </span>
              <span className="text-sm font-medium">
                {health.vehicle_info?.age_years || '-'} {t('common.years') || 'years'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-[var(--color-border)]">
              <span className="text-sm text-[var(--color-text-secondary)]">
                {t('vehicleHealth.currentMileage') || 'Current Mileage'}
              </span>
              <span className="text-sm font-medium">
                {health.vehicle_info?.current_mileage?.toLocaleString() || 0} {health.vehicle_info?.distance_unit || 'km'}
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-[var(--color-border)]">
              <span className="text-sm text-[var(--color-text-secondary)]">
                {t('vehicleHealth.fuelType') || 'Fuel Type'}
              </span>
              <span className="text-sm font-medium capitalize">
                {health.vehicle_info?.fuel_type || '-'}
              </span>
            </div>
            
            {/* Under warranty (F2) — real ledger from stored warranty dates/mileage */}
            <div className="mt-4 bg-purple-500/10 border border-purple-500/20 rounded-lg p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-purple-600 dark:text-purple-400">
                  {t('warranty.title') || 'Under warranty'}
                </p>
                {warranties.length > 0 && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-700 dark:text-purple-300 tabular-nums shrink-0">
                    {warranties.length}
                  </span>
                )}
              </div>
              {warranties.length === 0 ? (
                <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
                  {t('warranty.none') || 'No active warranties on record.'}
                </p>
              ) : (
                <ul className="mt-3 space-y-2" role="list">
                  {warranties.map((w) => {
                    const soon = w.days_left != null && w.days_left <= 30
                    const unit = health?.vehicle_info?.distance_unit || 'km'
                    return (
                      <li key={`${w.source_type}-${w.id}`} className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-[var(--color-text-primary)] truncate capitalize">
                            {w.label}
                          </p>
                          <p className="text-xs text-[var(--color-text-muted)]">
                            {w.days_left != null && (
                              <span>{(t('warranty.expiresIn') || 'Expires in {n} days').replace('{n}', w.days_left)}</span>
                            )}
                            {w.km_left != null && (
                              <span>
                                {w.days_left != null ? ' · ' : ''}
                                {(t('warranty.kmLeft') || '{n} {unit} left')
                                  .replace('{n}', Number(w.km_left).toLocaleString())
                                  .replace('{unit}', unit)}
                              </span>
                            )}
                          </p>
                        </div>
                        {soon && (
                          <span className="shrink-0 text-2xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 whitespace-nowrap">
                            {t('warranty.expiringSoon') || 'Expiring soon'}
                          </span>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>
        </ExpandableCard>
        
        {/* Cost Efficiency */}
        <ExpandableCard
          title={t('vehicleHealth.costEfficiency') || 'Cost Efficiency'}
          icon={Icons.trending}
          iconColor="bg-cyan-500/10 text-cyan-500"
          defaultExpanded={false}
        >
          <div className="pt-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.totalCosts') || 'Total Costs'}
                </p>
                <p className="text-xl font-bold mt-1">
                  {formatCurrency(health.cost_efficiency?.total_costs || 0)}
                </p>
              </div>
              <div className="bg-[var(--color-bg-tertiary)] rounded-lg p-3">
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.totalDistance') || 'Total Distance'}
                </p>
                <p className="text-xl font-bold mt-1">
                  {health.cost_efficiency?.total_distance_km?.toLocaleString() || 0} {health.vehicle_info?.distance_unit || 'km'}
                </p>
              </div>
            </div>
            
            {health.cost_efficiency?.cost_per_km && (
              <div className="bg-cyan-500/10 border border-cyan-500/20 rounded-xl p-4 text-center">
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {t('vehicleHealth.avgCostPerKm') || 'Average Cost Per Kilometer'}
                </p>
                <p className="text-3xl font-bold text-cyan-600 dark:text-cyan-400 mt-2">
                  {currency.symbol}{health.cost_efficiency.cost_per_km.toFixed(3)}
                </p>
              </div>
            )}
          </div>
        </ExpandableCard>
      </div>

      {/* Mark Done Modal */}
      {completingAction && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={handleCloseModal}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="mark-done-title"
            className="bg-[var(--color-bg-card)] rounded-2xl border border-[var(--color-border)] w-full max-w-sm shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="px-5 pt-5 pb-4 border-b border-[var(--color-border)]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-green-500/10 text-green-500 shrink-0">
                  {Icons.check}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 id="mark-done-title" className="font-semibold text-base">
                    {t('vehicleHealth.markDoneTitle') || 'Log Completed Service'}
                  </h3>
                  <p className="text-xs text-[var(--color-text-secondary)] truncate mt-0.5">
                    {translateAction(completingAction).title}
                  </p>
                </div>
              </div>
            </div>

            {/* Modal body */}
            <div className="px-5 py-4 space-y-4">
              {/* Mileage — optional */}
              <div>
                <label className="block text-sm font-medium mb-1.5">
                  {t('vehicleHealth.markDoneMileageOptional') || 'Mileage at Service (optional)'}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  min="0"
                  max="9999999"
                  value={completeForm.mileage}
                  onChange={(e) => setCompleteForm(prev => ({ ...prev, mileage: e.target.value }))}
                  placeholder={health.vehicle_info?.current_mileage?.toLocaleString() || ''}
                  className="input w-full"
                  disabled={completing}
                  aria-label={t('vehicleHealth.markDoneMileage') || 'Mileage at Service'}
                />
                <p className="text-xs text-[var(--color-text-secondary)] mt-1">
                  {t('vehicleHealth.currentMileage') || 'Current Mileage'}: {health.vehicle_info?.current_mileage?.toLocaleString() || '—'} {health.vehicle_info?.distance_unit || 'km'}
                </p>
              </div>

              {/* Notes — optional */}
              <div>
                <label className="block text-sm font-medium mb-1.5">
                  {t('vehicleHealth.markDoneNotes') || 'Notes (optional)'}
                </label>
                <textarea
                  rows={2}
                  value={completeForm.notes}
                  onChange={(e) => setCompleteForm(prev => ({ ...prev, notes: e.target.value }))}
                  className="input w-full resize-none"
                  disabled={completing}
                  maxLength={500}
                />
              </div>

              {/* Error */}
              {completeError && (
                <p className="text-xs text-red-500 bg-red-500/10 rounded-lg px-3 py-2">
                  {completeError}
                </p>
              )}

              {/* Success */}
              {completeSuccess && (
                <p className="text-xs text-green-600 dark:text-green-400 bg-green-500/10 rounded-lg px-3 py-2 flex items-center gap-2">
                  {Icons.check}
                  {t('vehicleHealth.markDoneSuccess') || 'Service recorded successfully'}
                </p>
              )}
            </div>

            {/* Modal footer */}
            <div className="px-5 pb-5 flex gap-3">
              <button
                onClick={handleCloseModal}
                disabled={completing}
                className="flex-1 btn btn-secondary"
              >
                {t('vehicleHealth.markDoneCancel') || 'Cancel'}
              </button>
              <button
                onClick={handleCompleteSubmit}
                disabled={completing || completeSuccess}
                className="flex-1 btn btn-primary flex items-center justify-center gap-2"
              >
                {completing ? (
                  <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                ) : (
                  Icons.check
                )}
                {t('vehicleHealth.markDoneConfirm') || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
