import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { vehicleApi, predictionApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import SeasonalChecklists from '../../components/recommendations/SeasonalChecklists'
import { formatDate } from '../../utils/dateFormat'
import { formatFuelEconomy } from '../../utils/fuelEconomy'

// SVG Icons
const Icons = {
  sparkle: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.912 5.813a2 2 0 001.275 1.275L21 12l-5.813 1.912a2 2 0 00-1.275 1.275L12 21l-1.912-5.813a2 2 0 00-1.275-1.275L3 12l5.813-1.912a2 2 0 001.275-1.275L12 3z"/>
    </svg>
  ),
  clock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  wrench: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  fuel: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17"/><path d="M15 22H3"/><path d="M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3"/>
      <rect x="6" y="6" width="6" height="5" rx="1"/>
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  car: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.8 1.1l-.8 1.63A6 6 0 0 0 2 12.42V16h2"/>
      <circle cx="6.5" cy="16.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>
    </svg>
  ),
  check: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  brain: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-1.66z"/>
      <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-1.66z"/>
    </svg>
  ),
  refresh: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
    </svg>
  ),
  dismiss: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  alertTriangle: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  odometer: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <path d="M12 8v4l3 3"/>
      <path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49"/>
    </svg>
  ),
}

export default function SmartRecommendations() {
  const { t, language } = useTranslation()
  const { user } = useAuth()
  const [recommendations, setRecommendations] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [vehicles, setVehicles] = useState([])

  // Mark Done state
  const [completingRec, setCompletingRec] = useState(null)
  const [recForm, setRecForm] = useState({ mileage: '', notes: '' })
  const [completing, setCompleting] = useState(false)
  const [recError, setRecError] = useState(null)
  const [recSuccess, setRecSuccess] = useState(false)

  // AI Predictions state
  const [aiPredictions, setAiPredictions] = useState([])      // stored Ollama alerts
  const [aiEnabled, setAiEnabled] = useState(null)            // null = unknown, true/false
  const [aiGenerating, setAiGenerating] = useState({})        // { [vehicleId]: true/false }
  const [aiErrors, setAiErrors] = useState({})                // { [vehicleId]: 'message' }
  // Stale / offline state per vehicle
  const [aiStaleMeta, setAiStaleMeta] = useState({})          // { [vehicleId]: { last_updated_at, offline } }
  // Retry countdown state: { [vehicleId]: { countdown: seconds, attempts: number } }
  const [aiRetry, setAiRetry] = useState({})
  const retryTimers = useRef({})                               // interval handles

  // Map frontend language codes to backend locale identifiers
  const _localeMap = { en: 'en-US', ro: 'ro', es: 'es' }
  const locale = _localeMap[language] || 'en-US'

  // Pick the right localized title from a stored prediction object
  const getAiTitle = useCallback((pred) => {
    if (language === 'ro' && pred.title_ro) return pred.title_ro
    if (language === 'es' && pred.title_es) return pred.title_es
    return pred.title_en || pred.title || ''
  }, [language])

  // Pick the right localized description
  const getAiDescription = useCallback((pred) => {
    if (language === 'ro' && pred.description_ro) return pred.description_ro
    if (language === 'es' && pred.description_es) return pred.description_es
    return pred.description_en || pred.description || ''
  }, [language])

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch all vehicles
        const vehiclesRes = await vehicleApi.getAll()
        const vehiclesList = vehiclesRes.data.vehicles || []
        setVehicles(vehiclesList)

        // Fetch stats for each vehicle to get rule-engine predictions
        const allRecommendations = []
        
        for (const vehicle of vehiclesList) {
          try {
            const statsRes = await vehicleApi.getStats(vehicle.id)
            const stats = statsRes.data
            
            // Generate predictions based on vehicle data
            const vehiclePredictions = generatePredictions(vehicle, stats)
            allRecommendations.push(...vehiclePredictions)
          } catch (err) {
            console.error(`Failed to fetch stats for vehicle ${vehicle.id}:`, err)
          }
        }

        // Sort by priority and days until due
        allRecommendations.sort((a, b) => {
          const priorityOrder = { high: 0, medium: 1, low: 2 }
          if (priorityOrder[a.priority] !== priorityOrder[b.priority]) {
            return priorityOrder[a.priority] - priorityOrder[b.priority]
          }
          return (a.daysUntil || 999) - (b.daysUntil || 999)
        })

        setRecommendations(allRecommendations)

        // Load AI status + stored Ollama predictions in parallel (non-blocking)
        try {
          const [statusRes, predsRes] = await Promise.all([
            predictionApi.getStatus(),
            predictionApi.getAll(null, 'active', locale),
          ])
          setAiEnabled(statusRes.data?.enabled ?? false)
          setAiPredictions(predsRes.data?.predictions || [])
        } catch (_aiErr) {
          // AI section is non-critical — rule-engine alerts still show
          setAiEnabled(false)
        }
      } catch (error) {
        console.error('Failed to fetch data:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleMarkDone = (rec, e) => {
    e.preventDefault()
    e.stopPropagation()
    setCompletingRec(rec)
    setRecForm({ mileage: '', notes: '' })
    setRecError(null)
    setRecSuccess(false)
  }

  const handleCompleteSubmit = async () => {
    if (!completingRec) return
    setCompleting(true)
    setRecError(null)
    try {
      const payload = {
        component: 'general_service',
      }
      if (recForm.mileage !== '') {
        const mileageInt = parseInt(recForm.mileage, 10)
        if (!isNaN(mileageInt) && mileageInt > 0) {
          payload.mileage = mileageInt
        }
      }
      if (recForm.notes.trim()) {
        payload.notes = recForm.notes.trim()
      }
      await vehicleApi.completeHealthAction(completingRec.vehicleId, payload)
      setRecSuccess(true)
      setTimeout(() => {
        setRecommendations(prev => prev.filter(r => r.id !== completingRec.id))
        setCompletingRec(null)
        setRecSuccess(false)
      }, 1000)
    } catch (err) {
      setRecError(err.response?.data?.error || t('common.failed') || 'Failed. Please try again.')
    } finally {
      setCompleting(false)
    }
  }

  const handleCloseRecModal = () => {
    if (completing) return
    setCompletingRec(null)
    setRecError(null)
    setRecSuccess(false)
  }

  // -----------------------------------------------------------------------
  // Retry countdown timer — decrements every second, cleared on success
  // -----------------------------------------------------------------------
  const _startRetryCountdown = useCallback((vehicleId, delaySeconds) => {
    // Clear any existing timer for this vehicle
    if (retryTimers.current[vehicleId]) {
      clearInterval(retryTimers.current[vehicleId])
    }
    setAiRetry(prev => ({ ...prev, [vehicleId]: { ...prev[vehicleId], countdown: delaySeconds } }))
    retryTimers.current[vehicleId] = setInterval(() => {
      setAiRetry(prev => {
        const cur = prev[vehicleId]
        if (!cur || cur.countdown <= 1) {
          clearInterval(retryTimers.current[vehicleId])
          delete retryTimers.current[vehicleId]
          return { ...prev, [vehicleId]: { ...cur, countdown: 0 } }
        }
        return { ...prev, [vehicleId]: { ...cur, countdown: cur.countdown - 1 } }
      })
    }, 1000)
  }, [])

  // Clean up timers on unmount
  useEffect(() => {
    const timers = retryTimers.current
    return () => { Object.values(timers).forEach(clearInterval) }
  }, [])

  const handleGenerateAi = async (vehicleId) => {
    // If retry countdown is still running, block the call
    const retryState = aiRetry[vehicleId]
    if (retryState?.countdown > 0) return

    setAiGenerating(prev => ({ ...prev, [vehicleId]: true }))
    setAiErrors(prev => ({ ...prev, [vehicleId]: null }))
    try {
      const res = await predictionApi.refresh(vehicleId, locale, true)
      const data = res.data || {}
      const newPreds = data.predictions || []

      // Merge new predictions in, replacing any prior ones for this vehicle
      setAiPredictions(prev => [
        ...prev.filter(p => p.vehicle_id !== vehicleId),
        ...newPreds,
      ])

      if (data.ollama_offline || data.stale) {
        // Ollama was unreachable — we got stale DB predictions back
        setAiStaleMeta(prev => ({
          ...prev,
          [vehicleId]: { last_updated_at: data.last_updated_at, offline: true },
        }))
        // Start a gentle backoff countdown so the retry button isn't hammered
        const attempts = (retryState?.attempts || 0) + 1
        const delay = Math.min(30 * Math.pow(2, attempts - 1), 300) // 30→60→120→240→300 s
        setAiRetry(prev => ({ ...prev, [vehicleId]: { attempts, countdown: 0 } }))
        _startRetryCountdown(vehicleId, delay)
      } else {
        // Fresh successful result — clear stale/retry state
        setAiStaleMeta(prev => { const n = { ...prev }; delete n[vehicleId]; return n })
        setAiRetry(prev => { const n = { ...prev }; delete n[vehicleId]; return n })
        if (retryTimers.current[vehicleId]) {
          clearInterval(retryTimers.current[vehicleId])
          delete retryTimers.current[vehicleId]
        }
      }
    } catch (err) {
      const status = err.response?.status
      const msg =
        status === 429 ? t('aiPredictions.rateLimited')
        : status === 503 ? (t('aiPredictions.offlineNoCache') || 'AI offline — no cached data available')
        : err.response?.data?.error || t('aiPredictions.generateError')
      setAiErrors(prev => ({ ...prev, [vehicleId]: msg }))
      // Exponential backoff on hard errors too
      const attempts = (aiRetry[vehicleId]?.attempts || 0) + 1
      const delay = Math.min(30 * Math.pow(2, attempts - 1), 300)
      setAiRetry(prev => ({ ...prev, [vehicleId]: { attempts, countdown: 0 } }))
      _startRetryCountdown(vehicleId, delay)
    } finally {
      setAiGenerating(prev => ({ ...prev, [vehicleId]: false }))
    }
  }

  const handleDismissAi = async (predictionId) => {
    try {
      await predictionApi.dismiss(predictionId)
      setAiPredictions(prev => prev.filter(p => p.id !== predictionId))
    } catch (_) {
      // silently ignore — prediction still shows until next page load
    }
  }

  const generatePredictions = (vehicle, stats) => {
    const predictions = []
    const today = new Date()

    // Next service due
    if (stats?.next_service_days !== null && stats?.next_service_days !== undefined) {
      predictions.push({
        id: `service-${vehicle.id}`,
        vehicleId: vehicle.id,
        vehicleName: vehicle.name,
        type: 'service_due',
        title: stats.next_service_title || t('smartRecommendations.serviceDue') || 'Service Due',
        description: stats.next_service,
        daysUntil: stats.next_service_days,
        priority: stats.next_service_days <= 7 ? 'high' : stats.next_service_days <= 30 ? 'medium' : 'low',
        icon: Icons.wrench,
        color: 'text-blue-500',
        bgColor: 'bg-blue-500/10',
      })
    }

    // Insurance expiry
    if (vehicle?.insurance_expiry) {
      const expiryDate = new Date(vehicle.insurance_expiry)
      const daysUntil = Math.ceil((expiryDate - today) / (1000 * 60 * 60 * 24))
      
      if (daysUntil <= 60 && daysUntil > 0) {
        predictions.push({
          id: `insurance-${vehicle.id}`,
          vehicleId: vehicle.id,
          vehicleName: vehicle.name,
          type: 'insurance_expiry',
          title: t('smartRecommendations.insuranceExpiry') || 'Insurance Expiry',
          description: formatDate(expiryDate),
          daysUntil,
          priority: daysUntil <= 14 ? 'high' : daysUntil <= 30 ? 'medium' : 'low',
          icon: Icons.shield,
          color: 'text-green-500',
          bgColor: 'bg-green-500/10',
        })
      }
    }

    // Tax due
    if (vehicle?.tax_due_date) {
      const dueDate = new Date(vehicle.tax_due_date)
      const daysUntil = Math.ceil((dueDate - today) / (1000 * 60 * 60 * 24))
      
      if (daysUntil <= 60 && daysUntil > 0) {
        predictions.push({
          id: `tax-${vehicle.id}`,
          vehicleId: vehicle.id,
          vehicleName: vehicle.name,
          type: 'tax_due',
          title: t('smartRecommendations.taxDue') || 'Tax Due',
          description: formatDate(dueDate),
          daysUntil,
          priority: daysUntil <= 14 ? 'high' : daysUntil <= 30 ? 'medium' : 'low',
          icon: Icons.clock,
          color: 'text-rose-500',
          bgColor: 'bg-rose-500/10',
        })
      }
    }

    // Fuel efficiency alert — direction depends on display unit:
    //   L/100km: higher value = worse → flag if > 12
    //   MPG:     lower value = worse  → flag if < 28  (28 MPG ≈ 12 L/100km)
    const _fuelUnit = stats?.fuel_economy_unit || 'L/100km'
    const _highConsumption = stats?.avg_consumption && (
      _fuelUnit === 'mpg'
        ? stats.avg_consumption < 28
        : stats.avg_consumption > 12
    )
    if (_highConsumption) {
      predictions.push({
        id: `fuel-${vehicle.id}`,
        vehicleId: vehicle.id,
        vehicleName: vehicle.name,
        type: 'fuel_efficiency',
        title: t('smartRecommendations.highFuelConsumption') || 'High Fuel Consumption',
        description: formatFuelEconomy(stats.avg_consumption, vehicle.distance_unit || user?.distance_unit),
        priority: 'low',
        icon: Icons.fuel,
        color: 'text-amber-500',
        bgColor: 'bg-amber-500/10',
      })
    }

    return predictions

  }

  const getPriorityBadge = (priority) => {
    const styles = {
      high: 'bg-red-500/20 text-red-500',
      medium: 'bg-amber-500/20 text-amber-500',
      low: 'bg-green-500/20 text-green-500',
    }
    const labels = {
      high: t('smartRecommendations.urgent') || 'Urgent',
      medium: t('smartRecommendations.soon') || 'Soon',
      low: t('smartRecommendations.info') || 'Info',
    }
    return (
      <span className={`text-2xs px-2 py-0.5 rounded-full font-medium ${styles[priority]}`}>
        {labels[priority]}
      </span>
    )
  }

  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-8 w-48 rounded-lg mb-4" />
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="skeleton h-20 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 pb-24">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500 shrink-0">
          {Icons.sparkle}
        </div>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold">{t('smartRecommendations.title') || 'Smart Recommendations'}</h1>
          <p className="text-xs text-[var(--color-text-secondary)]">
            {t('smartRecommendations.subtitle') || 'AI-powered insights for your vehicles'}
          </p>
        </div>
      </div>

      {/* Seasonal Checklists Section */}
      <div className="mb-6">
        <SeasonalChecklists showOnlyInSeason={false} />
      </div>

      {/* Vehicle Recommendations Section */}
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">
          {t('smartRecommendations.vehicleAlerts') || 'Vehicle Alerts'}
        </h2>
      </div>

      {/* Recommendations List */}
      {recommendations.length === 0 ? (
        <div className="card text-center py-12">
          <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-4">
            <span className="text-green-500">{Icons.check}</span>
          </div>
          <h3 className="text-sm font-medium mb-1">
            {t('smartRecommendations.allGood') || 'All Good!'}
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)]">
            {t('smartRecommendations.noRecommendations') || 'No urgent recommendations for your vehicles'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {recommendations.map(rec => {
            const canMarkDone = rec.type === 'service_due'
            const cardContent = (
              <>
                <div className={`w-10 h-10 rounded-xl ${rec.bgColor} flex items-center justify-center flex-shrink-0 ${rec.color}`}>
                  {rec.icon}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="text-sm font-medium truncate">{rec.title}</p>
                    {getPriorityBadge(rec.priority)}
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                    <span className="text-[var(--color-text-muted)]">{Icons.car}</span>
                    {rec.vehicleName}
                  </p>
                  {rec.daysUntil !== undefined && (
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      {rec.daysUntil <= 0 
                        ? t('smartRecommendations.overdue') || 'Overdue'
                        : `${rec.daysUntil} ${t('common.days') || 'days'} ${t('smartRecommendations.remaining') || 'remaining'}`
                      }
                    </p>
                  )}
                </div>
              </>
            )

            if (canMarkDone) {
              return (
                <div key={rec.id} className="card flex items-start gap-3 touch-manipulation">
                  <Link
                    to={`/vehicles/${rec.vehicleId}`}
                    className="flex items-start gap-3 flex-1 min-w-0"
                  >
                    {cardContent}
                  </Link>
                  <button
                    onClick={(e) => handleMarkDone(rec, e)}
                    className="shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border border-green-500/40 text-green-600 dark:text-green-400 bg-green-500/10 hover:bg-green-500/20 active:scale-95 transition-all touch-manipulation self-center"
                    aria-label={`${t('vehicleHealth.markDone') || 'Mark as Done'}: ${rec.title}`}
                  >
                    {Icons.check}
                    <span className="hidden sm:inline">{t('vehicleHealth.markDone') || 'Done'}</span>
                  </button>
                </div>
              )
            }

            return (
              <Link
                key={rec.id}
                to={`/vehicles/${rec.vehicleId}`}
                className="card flex items-start gap-3 touch-manipulation"
              >
                {cardContent}
                <span className="material-icons-outlined icon-sm text-[var(--color-text-muted)] flex-shrink-0">
                  chevron_right
                </span>
              </Link>
            )
          })}
        </div>
      )}

      {/* Summary */}
      {recommendations.length > 0 && (
        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="card text-center py-3">
            <p className="text-lg font-semibold text-red-500">
              {recommendations.filter(r => r.priority === 'high').length}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('smartRecommendations.urgent') || 'Urgent'}
            </p>
          </div>
          <div className="card text-center py-3">
            <p className="text-lg font-semibold text-amber-500">
              {recommendations.filter(r => r.priority === 'medium').length}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('smartRecommendations.soon') || 'Soon'}
            </p>
          </div>
          <div className="card text-center py-3">
            <p className="text-lg font-semibold text-green-500">
              {recommendations.filter(r => r.priority === 'low').length}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('smartRecommendations.info') || 'Info'}
            </p>
          </div>
        </div>
      )}

      {/* ── AI Analysis Section ── */}
      {aiEnabled !== false && (
        <div className="mt-8">
          {/* Section header */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-purple-500">{Icons.brain}</span>
              <h2 className="text-sm font-semibold">
                {t('smartRecommendations.aiInsightsTitle') || 'AI Insights'}
              </h2>
              <span className="text-2xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 font-medium">
                Ollama
              </span>
            </div>
          </div>

          {/* Per-vehicle generate buttons */}
          {vehicles.length > 0 && (
            <div className="space-y-2 mb-4">
              {vehicles.map(vehicle => {
                const isGenerating = !!aiGenerating[vehicle.id]
                const errMsg = aiErrors[vehicle.id]
                const staleMeta = aiStaleMeta[vehicle.id]
                const retryState = aiRetry[vehicle.id]
                const countdown = retryState?.countdown || 0
                const hasPreds = aiPredictions.some(p => p.vehicle_id === vehicle.id)
                const isStale = !!staleMeta?.offline

                // "Last updated X ago" label
                let lastUpdatedLabel = null
                if (staleMeta?.last_updated_at) {
                  const dt = new Date(staleMeta.last_updated_at)
                  const diffH = Math.round((Date.now() - dt.getTime()) / 3_600_000)
                  const diffD = Math.round(diffH / 24)
                  const agoStr = diffD >= 1
                    ? `${diffD}d`
                    : diffH >= 1 ? `${diffH}h` : '<1h'
                  lastUpdatedLabel = (t('aiPredictions.lastUpdated') || 'Last updated {ago}')
                    .replace('{ago}', agoStr)
                }

                return (
                  <div key={vehicle.id} className="card space-y-2 py-3">
                    <div className="flex items-center gap-3">
                      <span className="text-[var(--color-text-muted)] shrink-0">{Icons.car}</span>
                      <span className="flex-1 text-sm font-medium truncate">{vehicle.name || `${vehicle.year} ${vehicle.make} ${vehicle.model}`}</span>
                      {errMsg && !isStale && (
                        <span className="text-xs text-red-400 truncate max-w-[140px]" title={errMsg}>
                          {errMsg}
                        </span>
                      )}
                      <button
                        onClick={() => handleGenerateAi(vehicle.id)}
                        disabled={isGenerating || countdown > 0}
                        className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/30 hover:bg-purple-500/20 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation"
                        aria-label={`${isStale ? (t('aiPredictions.retryNow') || 'Retry') : hasPreds ? (t('smartRecommendations.reAnalyze') || 'Re-analyze') : (t('smartRecommendations.analyzeVehicle') || 'Analyze')}: ${vehicle.name}`}
                      >
                        {isGenerating ? (
                          <span className="w-3.5 h-3.5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
                        ) : (
                          Icons.refresh
                        )}
                        {isGenerating
                          ? null
                          : countdown > 0
                            ? (t('aiPredictions.retryIn') || 'Retry in {s}s').replace('{s}', countdown)
                            : isStale
                              ? (t('aiPredictions.retryNow') || 'Retry')
                              : hasPreds
                                ? (t('smartRecommendations.reAnalyze') || 'Re-analyze')
                                : (t('smartRecommendations.analyzeVehicle') || 'Analyze')}
                      </button>
                    </div>

                    {/* Stale data notice */}
                    {isStale && (
                      <div className="flex items-start gap-2 px-1 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                        <svg className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                        </svg>
                        <div className="min-w-0">
                          <p className="text-xs text-amber-600 dark:text-amber-400 leading-snug">
                            {t('aiPredictions.offlineStale') || 'Showing saved predictions — Ollama is currently offline'}
                          </p>
                          {lastUpdatedLabel && (
                            <p className="text-xs text-amber-500/80 mt-0.5">{lastUpdatedLabel}</p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Hard error (no stale data available) */}
                    {errMsg && !isStale && countdown > 0 && (
                      <p className="text-xs text-[var(--color-text-muted)] px-1">
                        {(t('aiPredictions.retryIn') || 'Retry in {s}s').replace('{s}', countdown)}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Stored AI prediction cards */}
          {aiPredictions.length === 0 ? (
            <div className="card text-center py-8 border-dashed border-purple-500/20">
              <div className="w-12 h-12 rounded-full bg-purple-500/10 flex items-center justify-center mx-auto mb-3 text-purple-400">
                {Icons.brain}
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {t('smartRecommendations.noAiPredictions') || 'No AI predictions yet. Tap Analyze to generate insights.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {aiPredictions.map(pred => {
                const urgencyColors = {
                  high: { text: 'text-red-500', bg: 'bg-red-500/10', badge: 'bg-red-500/20 text-red-500' },
                  medium: { text: 'text-amber-500', bg: 'bg-amber-500/10', badge: 'bg-amber-500/20 text-amber-500' },
                  low: { text: 'text-blue-500', bg: 'bg-blue-500/10', badge: 'bg-blue-500/20 text-blue-500' },
                }
                const uc = urgencyColors[pred.urgency] || urgencyColors.low
                const vehicleName = vehicles.find(v => v.id === pred.vehicle_id)?.name
                  || `${vehicles.find(v => v.id === pred.vehicle_id)?.year ?? ''} ${vehicles.find(v => v.id === pred.vehicle_id)?.make ?? ''}`.trim()
                  || `Vehicle #${pred.vehicle_id}`

                return (
                  <div key={pred.id} className="card flex items-start gap-3">
                    {/* Type icon */}
                    <div className={`w-10 h-10 rounded-xl ${uc.bg} flex items-center justify-center flex-shrink-0 ${uc.text}`}>
                      {pred.alert_type === 'fuel' ? Icons.fuel
                        : pred.alert_type === 'repair' ? Icons.wrench
                        : pred.alert_type === 'service' ? Icons.wrench
                        : Icons.alertTriangle}
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Title row */}
                      <div className="flex items-start gap-2 mb-0.5">
                        <p className="text-sm font-medium leading-snug">{getAiTitle(pred)}</p>
                        <span className={`shrink-0 text-2xs px-1.5 py-0.5 rounded-full font-medium ${uc.badge}`}>
                          {pred.urgency
                            ? (t(`smartRecommendations.urgency_${pred.urgency}`) || pred.urgency)
                            : null}
                        </span>
                      </div>

                      {/* Vehicle label */}
                      <p className="text-xs text-[var(--color-text-muted)] flex items-center gap-1 mb-1">
                        <span className="shrink-0">{Icons.car}</span>
                        {vehicleName}
                      </p>

                      {/* Description */}
                      {getAiDescription(pred) && (
                        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed mb-1">
                          {getAiDescription(pred)}
                        </p>
                      )}

                      {/* Footer row: cost estimate + confidence + mileage estimate + AI badge */}
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                        {pred.estimated_cost != null && (
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {t('smartRecommendations.estimatedCost') || 'Est. cost'}: {pred.estimated_cost}
                          </span>
                        )}
                        {pred.confidence_score != null && (
                          <span className="text-xs text-[var(--color-text-muted)]">
                            {t('smartRecommendations.confidence') || 'Confidence'}: {Math.round(pred.confidence_score * 100)}%
                          </span>
                        )}
                        {pred.predicted_mileage != null && (() => {
                          const predVehicle = vehicles.find(v => v.id === pred.vehicle_id)
                          const currentMileage = predVehicle?.current_mileage || 0
                          const distUnit = predVehicle?.distance_unit || 'km'
                          const diff = pred.predicted_mileage - currentMileage
                          return (
                            <span className="flex items-center gap-0.5 text-xs text-cyan-400">
                              {Icons.odometer}
                              {diff > 0
                                ? `${t('smartRecommendations.mileageIn') || 'In ~'}${diff.toLocaleString()} ${distUnit}`
                                : (t('smartRecommendations.mileageDue') || 'Threshold reached')}
                            </span>
                          )
                        })()}
                        <span className="text-2xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                          {Icons.sparkle} AI
                        </span>
                        {/* Stale badge shown when Ollama was offline for this vehicle */}
                        {aiStaleMeta[pred.vehicle_id]?.offline && (
                          <span className="text-2xs px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                            {t('aiPredictions.staleBadge') || 'Offline cache'}
                          </span>
                        )}
                      </div>

                      {/* Recommended action */}
                      {pred.recommended_action && (
                        <p className="mt-2 text-xs font-medium text-[var(--color-text-secondary)] border-l-2 border-purple-500/40 pl-2">
                          {pred.recommended_action}
                        </p>
                      )}
                    </div>

                    {/* Dismiss button */}
                    <button
                      onClick={() => handleDismissAi(pred.id)}
                      className="shrink-0 p-1.5 rounded-lg text-[var(--color-text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors touch-manipulation"
                      aria-label={t('common.dismiss') || 'Dismiss'}
                    >
                      {Icons.dismiss}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* AI disabled notice */}
      {aiEnabled === false && (
        <div className="mt-8 card border border-dashed border-[var(--color-border)] py-6 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            {t('aiPredictions.disabled') || 'AI predictions are not enabled on this server.'}
          </p>
        </div>
      )}

      {/* Mark Done Modal */}
      {completingRec && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={handleCloseRecModal}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="rec-mark-done-title"
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
                  <h3 id="rec-mark-done-title" className="font-semibold text-base">
                    {t('vehicleHealth.markDoneTitle') || 'Log Completed Service'}
                  </h3>
                  <p className="text-xs text-[var(--color-text-secondary)] truncate mt-0.5">
                    {completingRec.title} — {completingRec.vehicleName}
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
                  value={recForm.mileage}
                  onChange={(e) => setRecForm(prev => ({ ...prev, mileage: e.target.value }))}
                  className="input w-full"
                  disabled={completing}
                  aria-label={t('vehicleHealth.markDoneMileage') || 'Mileage at Service'}
                />
              </div>

              {/* Notes — optional */}
              <div>
                <label className="block text-sm font-medium mb-1.5">
                  {t('vehicleHealth.markDoneNotes') || 'Notes (optional)'}
                </label>
                <textarea
                  rows={2}
                  value={recForm.notes}
                  onChange={(e) => setRecForm(prev => ({ ...prev, notes: e.target.value }))}
                  className="input w-full resize-none"
                  disabled={completing}
                  maxLength={500}
                />
              </div>

              {/* Error */}
              {recError && (
                <p className="text-xs text-red-500 bg-red-500/10 rounded-lg px-3 py-2">
                  {recError}
                </p>
              )}

              {/* Success */}
              {recSuccess && (
                <p className="text-xs text-green-600 dark:text-green-400 bg-green-500/10 rounded-lg px-3 py-2 flex items-center gap-2">
                  {Icons.check}
                  {t('vehicleHealth.markDoneSuccess') || 'Service recorded successfully'}
                </p>
              )}
            </div>

            {/* Modal footer */}
            <div className="px-5 pb-5 flex gap-3">
              <button
                onClick={handleCloseRecModal}
                disabled={completing}
                className="flex-1 btn btn-secondary"
              >
                {t('vehicleHealth.markDoneCancel') || 'Cancel'}
              </button>
              <button
                onClick={handleCompleteSubmit}
                disabled={completing || recSuccess}
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
