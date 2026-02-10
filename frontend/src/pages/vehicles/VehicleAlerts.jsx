import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'

// SVG Icons
const Icons = {
  arrowBack: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 19l-7-7 7-7"/>
    </svg>
  ),
  alert: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  check: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  clock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
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
  car: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.8 1.1l-.8 1.63A6 6 0 0 0 2 12.42V16h2"/>
      <circle cx="6.5" cy="16.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>
    </svg>
  ),
  calendar: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  receipt: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/>
      <path d="M16 8H8M16 12H8M10 16H8"/>
    </svg>
  ),
  trendUp: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
    </svg>
  ),
}

// Prediction types configuration
const predictionTypes = {
  service_due: {
    icon: Icons.wrench,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500',
  },
  oil_change: {
    icon: Icons.fuel,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500',
  },
  insurance_expiry: {
    icon: Icons.shield,
    color: 'text-teal-500',
    bgColor: 'bg-teal-500/10',
    borderColor: 'border-teal-500',
  },
  tax_due: {
    icon: Icons.receipt,
    color: 'text-rose-500',
    bgColor: 'bg-rose-500/10',
    borderColor: 'border-rose-500',
  },
  tire_rotation: {
    icon: Icons.car,
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500',
  },
  inspection: {
    icon: Icons.check,
    color: 'text-green-500',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500',
  },
  default: {
    icon: Icons.alert,
    color: 'text-orange-500',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500',
  }
}

export default function VehicleAlerts() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  
  const [vehicle, setVehicle] = useState(null)
  const [predictions, setPredictions] = useState([])
  const [stats, setStats] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [vehicleRes, statsRes] = await Promise.all([
          vehicleApi.getById(id),
          vehicleApi.getStats(id)
        ])
        setVehicle(vehicleRes.data)
        setStats(statsRes.data)
        
        // Generate predictions based on stats and vehicle data
        const generatedPredictions = generatePredictions(vehicleRes.data, statsRes.data)
        setPredictions(generatedPredictions)
      } catch (error) {
        console.error('Failed to fetch data:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [id, navigate])
  
  // Generate predictions based on vehicle data and stats
  const generatePredictions = (vehicle, stats) => {
    const predictions = []
    const today = new Date()
    
    // Next service prediction
    if (stats?.next_service_days !== null && stats?.next_service_days !== undefined) {
      predictions.push({
        id: 'next_service',
        type: 'service_due',
        title: stats.next_service_title || t('alerts.serviceDue') || 'Service Due',
        description: stats.next_service || t('alerts.scheduledService') || 'Scheduled service',
        daysUntil: stats.next_service_days,
        priority: stats.next_service_days <= 7 ? 'high' : stats.next_service_days <= 30 ? 'medium' : 'low',
        date: stats.next_service,
      })
    }
    
    // Oil change prediction (every 10,000 km or 6 months)
    if (stats?.total_mileage) {
      const lastOilChange = stats.last_oil_change_mileage || 0
      const kmSinceOilChange = stats.total_mileage - lastOilChange
      const oilChangeInterval = 10000
      
      if (kmSinceOilChange > oilChangeInterval * 0.8) {
        const kmUntilOilChange = oilChangeInterval - (kmSinceOilChange % oilChangeInterval)
        predictions.push({
          id: 'oil_change',
          type: 'oil_change',
          title: t('alerts.oilChange') || 'Oil Change',
          description: `${kmUntilOilChange.toLocaleString()} km ${t('alerts.remaining') || 'remaining'}`,
          progress: Math.min(100, (kmSinceOilChange / oilChangeInterval) * 100),
          priority: kmSinceOilChange >= oilChangeInterval ? 'high' : 'medium',
        })
      }
    }
    
    // Insurance expiry (if we have insurance data)
    if (vehicle?.insurance_expiry) {
      const expiryDate = new Date(vehicle.insurance_expiry)
      const daysUntil = Math.ceil((expiryDate - today) / (1000 * 60 * 60 * 24))
      
      if (daysUntil <= 60) {
        predictions.push({
          id: 'insurance',
          type: 'insurance_expiry',
          title: t('alerts.insuranceExpiry') || 'Insurance Expiry',
          description: expiryDate.toLocaleDateString(),
          daysUntil,
          priority: daysUntil <= 14 ? 'high' : daysUntil <= 30 ? 'medium' : 'low',
          date: vehicle.insurance_expiry,
        })
      }
    }
    
    // Tax due (if we have tax data)
    if (vehicle?.tax_due_date) {
      const dueDate = new Date(vehicle.tax_due_date)
      const daysUntil = Math.ceil((dueDate - today) / (1000 * 60 * 60 * 24))
      
      if (daysUntil <= 60) {
        predictions.push({
          id: 'tax',
          type: 'tax_due',
          title: t('alerts.taxDue') || 'Tax Due',
          description: dueDate.toLocaleDateString(),
          daysUntil,
          priority: daysUntil <= 14 ? 'high' : daysUntil <= 30 ? 'medium' : 'low',
          date: vehicle.tax_due_date,
        })
      }
    }
    
    // Tire rotation (every 10,000 km)
    if (stats?.total_mileage) {
      const tireRotationInterval = 10000
      const kmSinceRotation = stats.total_mileage % tireRotationInterval
      
      if (kmSinceRotation > tireRotationInterval * 0.8) {
        predictions.push({
          id: 'tire_rotation',
          type: 'tire_rotation',
          title: t('alerts.tireRotation') || 'Tire Rotation',
          description: `${(tireRotationInterval - kmSinceRotation).toLocaleString()} km ${t('alerts.remaining') || 'remaining'}`,
          progress: (kmSinceRotation / tireRotationInterval) * 100,
          priority: 'low',
        })
      }
    }
    
    // Annual inspection
    if (vehicle?.last_inspection_date) {
      const lastInspection = new Date(vehicle.last_inspection_date)
      const nextInspection = new Date(lastInspection)
      nextInspection.setFullYear(nextInspection.getFullYear() + 1)
      const daysUntil = Math.ceil((nextInspection - today) / (1000 * 60 * 60 * 24))
      
      if (daysUntil <= 60) {
        predictions.push({
          id: 'inspection',
          type: 'inspection',
          title: t('alerts.inspection') || 'Vehicle Inspection',
          description: nextInspection.toLocaleDateString(),
          daysUntil,
          priority: daysUntil <= 14 ? 'high' : daysUntil <= 30 ? 'medium' : 'low',
        })
      }
    }
    
    // Sort by priority
    const priorityOrder = { high: 0, medium: 1, low: 2 }
    predictions.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
    
    return predictions
  }
  
  const getTypeStyle = (type) => {
    return predictionTypes[type] || predictionTypes.default
  }
  
  const getPriorityStyle = (priority) => {
    switch (priority) {
      case 'high':
        return { label: t('alerts.urgent') || 'Urgent', color: 'text-red-500', bg: 'bg-red-500/10' }
      case 'medium':
        return { label: t('alerts.soon') || 'Soon', color: 'text-amber-500', bg: 'bg-amber-500/10' }
      case 'low':
        return { label: t('alerts.upcoming') || 'Upcoming', color: 'text-green-500', bg: 'bg-green-500/10' }
      default:
        return { label: t('alerts.info') || 'Info', color: 'text-gray-500', bg: 'bg-gray-500/10' }
    }
  }
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-14 rounded-xl mb-4" />
        <div className="skeleton h-32 rounded-xl mb-4" />
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }
  
  const urgentCount = predictions.filter(p => p.priority === 'high').length
  const upcomingCount = predictions.filter(p => p.priority !== 'high').length
  
  return (
    <div className="pb-20">
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
            <h1 className="text-lg font-semibold">{t('alerts.title') || 'Prediction Alerts'}</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model}
            </p>
          </div>
        </div>
      </div>
      
      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-red-500/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              {Icons.alert}
              <span className="text-xs text-red-500 font-medium">
                {t('alerts.urgent') || 'Urgent'}
              </span>
            </div>
            <p className="text-2xl font-bold text-red-500">{urgentCount}</p>
          </div>
          
          <div className="bg-amber-500/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-1">
              {Icons.clock}
              <span className="text-xs text-amber-500 font-medium">
                {t('alerts.upcoming') || 'Upcoming'}
              </span>
            </div>
            <p className="text-2xl font-bold text-amber-500">{upcomingCount}</p>
          </div>
        </div>
        
        {/* Predictions list */}
        {predictions.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-500/10 flex items-center justify-center text-green-500">
              {Icons.check}
            </div>
            <h3 className="font-medium mb-1">{t('alerts.allGood') || 'All Good!'}</h3>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('alerts.noAlerts') || 'No upcoming maintenance alerts'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <h2 className="text-sm font-medium text-[var(--color-text-secondary)]">
              {t('alerts.predictions') || 'Predictions'}
            </h2>
            
            {predictions.map((prediction) => {
              const typeStyle = getTypeStyle(prediction.type)
              const priorityStyle = getPriorityStyle(prediction.priority)
              
              return (
                <div 
                  key={prediction.id}
                  className={`bg-[var(--color-bg-secondary)] rounded-xl p-4 border-l-4 ${typeStyle.borderColor}`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${typeStyle.bgColor} ${typeStyle.color}`}>
                      {typeStyle.icon}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium">{prediction.title}</h3>
                        <span className={`px-2 py-0.5 rounded-full text-2xs font-medium ${priorityStyle.bg} ${priorityStyle.color}`}>
                          {priorityStyle.label}
                        </span>
                      </div>
                      
                      <p className="text-sm text-[var(--color-text-secondary)] mb-2">
                        {prediction.description}
                      </p>
                      
                      {prediction.daysUntil !== undefined && (
                        <div className="flex items-center gap-2 text-xs">
                          {Icons.calendar}
                          <span className={prediction.daysUntil <= 7 ? 'text-red-500 font-medium' : 'text-[var(--color-text-secondary)]'}>
                            {prediction.daysUntil <= 0 
                              ? t('alerts.overdue') || 'Overdue!'
                              : `${prediction.daysUntil} ${t('common.days') || 'days'} ${t('alerts.remaining') || 'remaining'}`
                            }
                          </span>
                        </div>
                      )}
                      
                      {prediction.progress !== undefined && (
                        <div className="mt-2">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-[var(--color-text-secondary)]">
                              {t('alerts.progress') || 'Progress'}
                            </span>
                            <span className="font-medium">{Math.round(prediction.progress)}%</span>
                          </div>
                          <div className="h-2 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full transition-all ${
                                prediction.progress >= 90 ? 'bg-red-500' : 
                                prediction.progress >= 70 ? 'bg-amber-500' : 'bg-green-500'
                              }`}
                              style={{ width: `${Math.min(100, prediction.progress)}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        
        {/* Info card */}
        <div className="bg-[var(--color-bg-secondary)] rounded-xl p-4 mt-6">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500">
              {Icons.trendUp}
            </div>
            <div>
              <h3 className="font-medium mb-1">{t('alerts.howItWorks') || 'How It Works'}</h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {t('alerts.howItWorksDesc') || 'Predictions are based on your vehicle\'s mileage, service history, and typical maintenance intervals. Keep your records updated for accurate predictions.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
