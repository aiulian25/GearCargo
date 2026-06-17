import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import EmptyState from '../../components/ui/EmptyState'

export default function Vehicles() {
  const { t } = useTranslation()
  const [vehicles, setVehicles] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        setVehicles(response.data.vehicles || [])
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchVehicles()
  }, [])
  
  if (isLoading) {
    return (
      <div className="p-4 space-y-3">
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    )
  }
  
  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold">My Vehicles</h1>
        <Link to="/vehicles/add" className="btn btn-primary btn-sm">
          <span className="material-icons-outlined icon-sm">add</span>
          Add
        </Link>
      </div>
      
      {/* Vehicle List */}
      {vehicles.length === 0 ? (
        <EmptyState
          icon="directions_car"
          title={t('empty.vehiclesTitle') || 'No vehicles yet'}
          description={t('empty.vehiclesDesc') || 'Add your first vehicle to start tracking fuel, services and costs.'}
          actionLabel={t('empty.vehiclesCta') || 'Add your first vehicle'}
          actionTo="/vehicles/add"
        />
      ) : (
        <div className="space-y-3">
          {vehicles.map(vehicle => (
            <Link 
              key={vehicle.id} 
              to={`/vehicles/${vehicle.id}`}
              className="card flex items-center gap-4 touch-manipulation"
            >
              {/* Icon/Photo */}
              <div className="w-14 h-14 rounded-xl bg-[var(--color-bg-tertiary)] flex items-center justify-center flex-shrink-0">
                {vehicle.photo_url ? (
                  <img 
                    src={vehicle.photo_url} 
                    alt={vehicle.name}
                    className="w-full h-full object-cover rounded-xl"
                  />
                ) : (
                  <span className="material-icons-outlined icon-lg text-[var(--color-text-muted)]">
                    directions_car
                  </span>
                )}
              </div>
              
              {/* Info */}
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium truncate">{vehicle.name}</h3>
                <p className="text-xs text-[var(--color-text-secondary)]">
                  {vehicle.make} {vehicle.model}
                  {vehicle.year && ` • ${vehicle.year}`}
                </p>
                {vehicle.license_plate && (
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                    {vehicle.license_plate}
                  </p>
                )}
              </div>
              
              {/* Mileage */}
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold">
                  {vehicle.current_mileage?.toLocaleString() || 0}
                </p>
                <p className="text-2xs text-[var(--color-text-muted)]">{vehicle.distance_unit || 'km'}</p>
              </div>
              
              {/* Arrow */}
              <span className="material-icons-outlined icon-sm text-[var(--color-text-muted)]">
                chevron_right
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
