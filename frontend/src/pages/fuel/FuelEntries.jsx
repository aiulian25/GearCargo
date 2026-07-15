import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fuelApi, vehicleApi } from '../../services/api'
import { useAuth } from '../../contexts/AuthContext'
import { useTranslation } from '../../contexts/LanguageContext'
import { formatDate } from '../../utils/dateFormat'
import { formatFuelEconomy, getFuelEconomyUnit, resolveFuelSystem, litersToDisplayVolume, volumeUnitLabel } from '../../utils/fuelEconomy'
import EmptyState from '../../components/ui/EmptyState'

export default function FuelEntries() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const vehicleId = searchParams.get('vehicle')
  
  const [entries, setEntries] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [selectedVehicle, setSelectedVehicle] = useState(vehicleId || 'all')
  const [isLoading, setIsLoading] = useState(true)
  const [stats, setStats] = useState(null)
  // F26 — per-station insights (collapsible card above the entries list).
  const [stations, setStations] = useState([])
  const [showStations, setShowStations] = useState(true)
  const { user } = useAuth()

  const getVehicleDistanceUnit = (id) => {
    return vehicles.find(v => String(v.id) === String(id))?.distance_unit || 'km'
  }

  const selectedVehicleUnit = selectedVehicle === 'all'
    ? (user?.distance_unit || 'km')
    : getVehicleDistanceUnit(selectedVehicle)

  const avgFuelEconomy = stats?.avg_consumption ?? stats?.avg_efficiency ?? null

  // F16: MPG gallon system (US vs Imperial) follows the user's region.
  const fuelSystem = resolveFuelSystem({ country: user?.country_preference, currency: user?.currency })
  const mpgLabel = t(fuelSystem === 'us' ? 'units.mpgUs' : 'units.mpgUk') || 'MPG'
  const economyOpts = { system: fuelSystem, mpgLabel }
  const economyUnitLabel = (unit) =>
    getFuelEconomyUnit(unit) === 'MPG' ? mpgLabel : getFuelEconomyUnit(unit)
  
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
          ? await fuelApi.getAll()
          : await fuelApi.getByVehicle(selectedVehicle)
        setEntries(response.data.entries || [])
        setStats(response.data.stats || null)
      } catch (error) {
        console.error('Failed to fetch fuel entries:', error)
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchEntries()
  }, [selectedVehicle])

  // F26 — station aggregation; silent failure just hides the card.
  useEffect(() => {
    let cancelled = false
    fuelApi.getStations(selectedVehicle === 'all' ? null : selectedVehicle)
      .then(res => { if (!cancelled) setStations(res.data.stations || []) })
      .catch(() => { if (!cancelled) setStations([]) })
    return () => { cancelled = true }
  }, [selectedVehicle])

  // Best value = lowest average price among stations visited at least twice.
  const cheapestName = (() => {
    const eligible = stations.filter(s => s.fills >= 2 && s.avg_price != null)
    if (!eligible.length) return null
    return eligible.reduce((a, b) => (a.avg_price <= b.avg_price ? a : b)).name
  })()
  
  return (
    <div className="p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-semibold">Fuel Log</h1>
        <Link to="/fuel/add" className="btn btn-primary btn-sm">
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
      
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="card text-center py-3">
            <p className="text-lg font-bold text-[var(--color-accent)]">
              {formatFuelEconomy(avgFuelEconomy, selectedVehicleUnit, 1, economyOpts).split(' ')[0]}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">{economyUnitLabel(selectedVehicleUnit)}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-lg font-bold">
              {stats.total_liters != null
                ? litersToDisplayVolume(stats.total_liters, user).toFixed(0) : 0}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">{volumeUnitLabel(user, t)}</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-lg font-bold">
              {stats.total_cost?.toFixed(0) || 0}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">Total Cost</p>
          </div>
        </div>
      )}
      
      {/* Stations (F26) — the user's own per-station price picture */}
      {stations.length > 0 && (
        <div className="card mb-4">
          <button
            type="button"
            onClick={() => setShowStations(!showStations)}
            className="w-full flex items-center justify-between py-1"
            aria-expanded={showStations}
          >
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
              {t('stations.title') || 'Your stations'}
            </h3>
            <span className={`material-icons-outlined icon-sm text-[var(--color-text-muted)] transition-transform ${showStations ? 'rotate-180' : ''}`}>
              expand_more
            </span>
          </button>

          {showStations && (
            <div className="mt-2 divide-y divide-[var(--color-border)]">
              {stations.map(s => (
                <div key={s.name} className="flex items-center gap-3 py-2.5">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {s.name}
                      {s.name === cheapestName && (
                        <span className="ml-1.5 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-2xs font-semibold bg-green-500/15 text-green-600 dark:text-green-400 align-middle">
                          ★ {t('stations.cheapest') || 'Best value'}
                        </span>
                      )}
                    </p>
                    <p className="text-2xs text-[var(--color-text-muted)]">
                      {s.fills} {t('stations.fills') || 'fills'}
                      {s.last_date && ` • ${formatDate(s.last_date)}`}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-semibold tabular-nums whitespace-nowrap">
                      {s.avg_price != null ? s.avg_price.toFixed(2) : '--'}/L
                      <span className="ml-1 text-2xs font-normal text-[var(--color-text-muted)]">
                        {t('stations.avgPrice') || 'avg price'}
                      </span>
                    </p>
                    {s.delta_vs_national_pct != null && (
                      <p className={`text-2xs tabular-nums whitespace-nowrap ${s.delta_vs_national_pct <= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {s.delta_vs_national_pct > 0 ? '+' : ''}{s.delta_vs_national_pct.toFixed(1)}% {t('stations.vsNational') || 'vs national avg'}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
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
        <EmptyState
          icon="local_gas_station"
          title={t('empty.fuelTitle') || 'No fuel entries yet'}
          description={t('empty.fuelDesc') || 'Log your fill-ups to track consumption and spending.'}
          actionLabel={t('empty.fuelCta') || 'Add fuel entry'}
          actionTo="/fuel/add"
        />
      ) : (
        <div className="space-y-2">
          {entries.map(entry => (
            <Link 
              key={entry.id} 
              to={`/fuel/${entry.id}`}
              className="card flex items-center gap-3 touch-manipulation"
            >
              <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
                <span className="material-icons-outlined icon-sm text-amber-500">
                  local_gas_station
                </span>
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">
                    {entry.liters != null ? litersToDisplayVolume(entry.liters, user).toFixed(2) : '--'} {volumeUnitLabel(user, t)}
                  </p>
                  {entry.is_full_tank && (
                    <span className="badge badge-sm bg-green-500/10 text-green-500">Full</span>
                  )}
                </div>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {formatDate(entry.date)} • {entry.mileage?.toLocaleString()} {vehicles.find(v => v.id === entry.vehicle_id)?.distance_unit || 'km'}
                  {vehicles.length > 1 && entry.vehicle_name && ` • ${entry.vehicle_name}`}
                </p>
              </div>
              
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold">{entry.total_cost}</p>
                {entry.consumption && (
                  <p className="text-2xs text-[var(--color-text-muted)]">
                    {formatFuelEconomy(entry.consumption, getVehicleDistanceUnit(entry.vehicle_id), 1, economyOpts)}
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
