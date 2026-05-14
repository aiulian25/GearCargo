import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { fuelApi, vehicleApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { normalizeDistanceUnit } from '../../utils/fuelEconomy'

export default function AddFuel() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  const { t } = useTranslation()
  const { user } = useAuth()
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [isLoadingVehicles, setIsLoadingVehicles] = useState(true)
  
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      liters: '',
      price_per_liter: '',
      total_cost: '',
      is_full_tank: true,
      fuel_type: '',
      station_name: '',
      notes: '',
    }
  })
  
  const liters = watch('liters')
  const pricePerLiter = watch('price_per_liter')
  const selectedVehicleId = watch('vehicle_id')
  const selectedVehicle = vehicles.find(v => v.id === parseInt(selectedVehicleId))
  const distUnit = normalizeDistanceUnit(selectedVehicle?.distance_unit || user?.distance_unit) === 'miles' ? 'mi' : 'km'
  
  // Auto-calculate total cost
  useEffect(() => {
    if (liters && pricePerLiter) {
      const total = (parseFloat(liters) * parseFloat(pricePerLiter)).toFixed(2)
      setValue('total_cost', total)
    }
  }, [liters, pricePerLiter, setValue])
  
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        const vehicleList = response.data.vehicles || []
        setVehicles(vehicleList)
        
        // Auto-select first vehicle if only one
        if (vehicleList.length === 1 && !preselectedVehicle) {
          setValue('vehicle_id', vehicleList[0].id.toString())
        }
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      } finally {
        setIsLoadingVehicles(false)
      }
    }
    
    fetchVehicles()
  }, [preselectedVehicle, setValue])
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      await fuelApi.create({
        ...data,
        vehicle_id: parseInt(data.vehicle_id),
        mileage: parseInt(data.mileage),
        liters: parseFloat(data.liters),
        price_per_liter: parseFloat(data.price_per_liter),
        total_cost: parseFloat(data.total_cost),
      })
      
      navigate(-1)
    } catch (err) {
      setError(err.response?.data?.error || t('addFuel.error') || 'Failed to add fuel entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const fuelTypes = [
    { value: '', label: t('addFuel.fuelTypeDefault') || 'Default' },
    { value: 'petrol_95', label: t('addFuel.petrol95') || 'Petrol 95' },
    { value: 'petrol_98', label: t('addFuel.petrol98') || 'Petrol 98' },
    { value: 'petrol_100', label: t('addFuel.petrol100') || 'Petrol 100' },
    { value: 'diesel', label: t('addFuel.diesel') || 'Diesel' },
    { value: 'diesel_premium', label: t('addFuel.dieselPremium') || 'Premium Diesel' },
    { value: 'lpg', label: t('addFuel.lpg') || 'LPG' },
    { value: 'electric', label: t('addFuel.electric') || 'Electric (kWh)' },
  ]
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('addFuel.title') || 'Add Fuel'}</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting || isLoadingVehicles}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? (
            <span className="material-icons-outlined icon-sm animate-spin">sync</span>
          ) : (
            t('common.save') || 'Save'
          )}
        </button>
      </div>
      
      <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}
        
        {vehicles.length === 0 && !isLoadingVehicles && (
          <div className="bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 px-4 py-3 rounded-xl text-sm">
            {t('validation.addVehicleFirst') || 'You need to add a vehicle first before logging fuel.'}
          </div>
        )}
        
        {/* Vehicle & Date */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('common.vehicle') || 'Vehicle'} *
            </label>
            <select 
              {...register('vehicle_id', { required: t('validation.selectVehicle') || 'Select a vehicle' })}
              className="input"
              disabled={isLoadingVehicles}
            >
              <option value="">{t('common.selectVehicle') || 'Select vehicle'}</option>
              {vehicles.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            {errors.vehicle_id && (
              <p className="text-xs text-red-500 mt-1">{errors.vehicle_id.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.date') || 'Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addFuel.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.odometer') || 'Odometer'} ({distUnit}) *
              </label>
              <input
                type="number"
                {...register('mileage', { 
                  required: t('addFuel.mileageRequired') || 'Mileage is required',
                  min: { value: 0, message: t('addFuel.invalidMileage') || 'Invalid mileage' }
                })}
                className="input"
                placeholder="0"
              />
              {errors.mileage && (
                <p className="text-xs text-red-500 mt-1">{errors.mileage.message}</p>
              )}
            </div>
          </div>
        </div>
        
        {/* Fuel Details */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('addFuel.fuelDetails') || 'Fuel Details'}</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.liters') || 'Liters'} *
              </label>
              <input
                type="number"
                step="0.01"
                {...register('liters', { 
                  required: t('addFuel.litersRequired') || 'Liters is required',
                  min: { value: 0.01, message: t('addFuel.invalidAmount') || 'Invalid amount' }
                })}
                className="input"
                placeholder="0.00"
              />
              {errors.liters && (
                <p className="text-xs text-red-500 mt-1">{errors.liters.message}</p>
              )}
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.pricePerLiter') || 'Price/Liter'} *
              </label>
              <input
                type="number"
                step="0.001"
                {...register('price_per_liter', { 
                  required: t('addFuel.priceRequired') || 'Price is required',
                  min: { value: 0.01, message: t('addFuel.invalidPrice') || 'Invalid price' }
                })}
                className="input"
                placeholder="0.000"
              />
              {errors.price_per_liter && (
                <p className="text-xs text-red-500 mt-1">{errors.price_per_liter.message}</p>
              )}
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addFuel.totalCost') || 'Total Cost'}
            </label>
            <input
              type="number"
              step="0.01"
              {...register('total_cost')}
              className="input bg-[var(--color-bg-tertiary)]"
              placeholder={t('addFuel.calculatedAuto') || 'Calculated automatically'}
            />
          </div>
          
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="is_full_tank"
              {...register('is_full_tank')}
              className="w-5 h-5 rounded border-[var(--color-border)] text-[var(--color-accent)] focus:ring-[var(--color-accent)]"
            />
            <label htmlFor="is_full_tank" className="text-sm">
              {t('addFuel.fullTank') || 'Full tank fill-up'}
            </label>
          </div>
        </div>
        
        {/* Additional */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('addFuel.additional') || 'Additional'}</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.fuelType') || 'Fuel Type'}
              </label>
              <select {...register('fuel_type')} className="input">
                {fuelTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addFuel.station') || 'Station'}
              </label>
              <input
                type="text"
                {...register('station_name')}
                className="input"
                placeholder={t('addFuel.optional') || 'Optional'}
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addFuel.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addFuel.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
      </form>
    </div>
  )
}
