import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { repairApi, vehicleApi } from '../../services/api'

export default function Repairs() {
  const [searchParams] = useSearchParams()
  const vehicleId = searchParams.get('vehicle')
  
  const [entries, setEntries] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [selectedVehicle, setSelectedVehicle] = useState(vehicleId || 'all')
  const [isLoading, setIsLoading] = useState(true)
  
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        setVehicles(response.data.vehicles || [])
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      }
    }
    fetchVehicles()
  }, [])
  
  useEffect(() => {
    const fetchEntries = async () => {
      setIsLoading(true)
      try {
        const response = selectedVehicle === 'all' 
          ? await repairApi.getAll()
          : await repairApi.getByVehicle(selectedVehicle)
        setEntries(response.data.entries || [])
      } catch (error) {
        console.error('Failed to fetch repair entries:', error)
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchEntries()
  }, [selectedVehicle])
  
  const getCategoryIcon = (category) => {
    const icons = {
      engine: 'settings',
      transmission: 'sync_alt',
      brakes: 'do_not_disturb_on',
      suspension: 'height',
      electrical: 'electrical_services',
      exhaust: 'air',
      cooling: 'ac_unit',
      ac_heating: 'thermostat',
      steering: 'gesture',
      body: 'directions_car',
      interior: 'event_seat',
      tires_wheels: 'tire_repair',
    }
    return icons[category] || 'handyman'
  }
  
  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold">Repair Log</h1>
        <Link to="/repairs/add" className="btn btn-primary btn-sm">
          <span className="material-icons-outlined icon-sm">add</span>
          Add
        </Link>
      </div>
      
      {/* Vehicle Filter */}
      {vehicles.length > 1 && (
        <div className="mb-4">
          <select
            value={selectedVehicle}
            onChange={(e) => setSelectedVehicle(e.target.value)}
            className="input"
          >
            <option value="all">All Vehicles</option>
            {vehicles.map(v => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </div>
      )}
      
      {/* Entries List */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="skeleton h-16 rounded-xl" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <div className="card text-center py-12">
          <span className="material-icons-outlined icon-xl text-[var(--color-text-muted)] mb-3">
            handyman
          </span>
          <h3 className="text-sm font-medium mb-1">No repair entries</h3>
          <p className="text-xs text-[var(--color-text-secondary)] mb-4">
            Track repairs and issues
          </p>
          <Link to="/repairs/add" className="btn btn-primary">
            Add Repair Entry
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {entries.map(entry => (
            <Link 
              key={entry.id} 
              to={`/repairs/${entry.id}`}
              className="card flex items-center gap-3 touch-manipulation"
            >
              <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center flex-shrink-0">
                <span className="material-icons-outlined icon-sm text-red-500">
                  {getCategoryIcon(entry.category)}
                </span>
              </div>
              
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{entry.description}</p>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {entry.date} • {entry.mileage?.toLocaleString() || '-'} {vehicles.find(v => v.id === entry.vehicle_id)?.distance_unit || 'km'}
                  {vehicles.length > 1 && entry.vehicle_name && ` • ${entry.vehicle_name}`}
                </p>
                {entry.warranty_expires && (
                  <p className="text-2xs text-green-500">
                    Warranty until {entry.warranty_expires}
                  </p>
                )}
              </div>
              
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold">{entry.total_cost}</p>
                {entry.shop_name && (
                  <p className="text-2xs text-[var(--color-text-muted)] truncate max-w-[80px]">
                    {entry.shop_name}
                  </p>
                )}
              </div>
              
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
