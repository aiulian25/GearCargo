import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
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
}

export default function SmartRecommendations() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [recommendations, setRecommendations] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  // Mark Done state
  const [completingRec, setCompletingRec] = useState(null)
  const [recForm, setRecForm] = useState({ mileage: '', notes: '' })
  const [completing, setCompleting] = useState(false)
  const [recError, setRecError] = useState(null)
  const [recSuccess, setRecSuccess] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch all vehicles
        const vehiclesRes = await vehicleApi.getAll()
        const vehiclesList = vehiclesRes.data.vehicles || []

        // Fetch stats for each vehicle to get predictions
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
      } catch (error) {
        console.error('Failed to fetch data:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [])

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

    // Fuel efficiency alert (if significantly worse than average)
    if (stats?.avg_consumption && stats.avg_consumption > 12) {
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
        <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500">
          {Icons.sparkle}
        </div>
        <div>
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
