import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { serviceApi, vehicleApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { normalizeDistanceUnit } from '../../utils/fuelEconomy'

export default function AddService() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  const { t } = useTranslation()
  const { user } = useAuth()
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [selectedServiceTypes, setSelectedServiceTypes] = useState([])
  
  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      description: '',
      shop_name: '',
      labor_cost: '',
      parts_cost: '',
      total_cost: '',
      notes: '',
    }
  })
  
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        const vehicleList = response.data.vehicles || []
        setVehicles(vehicleList)
        
        if (vehicleList.length === 1 && !preselectedVehicle) {
          setValue('vehicle_id', vehicleList[0].id.toString())
        }
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      }
    }
    
    fetchVehicles()
  }, [preselectedVehicle, setValue])
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    // Validate multi-select service types
    if (selectedServiceTypes.length === 0) {
      setError(t('addService.typeRequired') || 'Service type is required')
      setIsSubmitting(false)
      return
    }
    
    try {
      await serviceApi.create({
        ...data,
        vehicle_id: parseInt(data.vehicle_id),
        service_types: selectedServiceTypes,
        service_type: selectedServiceTypes[0],
        mileage: data.mileage ? parseInt(data.mileage) : null,
        labor_cost: data.labor_cost ? parseFloat(data.labor_cost) : 0,
        parts_cost: data.parts_cost ? parseFloat(data.parts_cost) : 0,
        total_cost: data.total_cost ? parseFloat(data.total_cost) : 
          (parseFloat(data.labor_cost || 0) + parseFloat(data.parts_cost || 0)),
      })
      
      navigate(-1)
    } catch (err) {
      setError(err.response?.data?.error || t('addService.error') || 'Failed to add service entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const serviceTypes = [
    { value: 'oil_change', label: t('serviceTypes.oilChange') || 'Oil Change' },
    { value: 'tire_rotation', label: t('serviceTypes.tireRotation') || 'Tire Rotation' },
    { value: 'brake_service', label: t('serviceTypes.brakeService') || 'Brake Service' },
    { value: 'air_filter', label: t('serviceTypes.airFilter') || 'Air Filter' },
    { value: 'cabin_filter', label: t('serviceTypes.cabinFilter') || 'Cabin Filter' },
    { value: 'spark_plugs', label: t('serviceTypes.sparkPlugs') || 'Spark Plugs' },
    { value: 'transmission', label: t('serviceTypes.transmission') || 'Transmission Service' },
    { value: 'coolant', label: t('serviceTypes.coolant') || 'Coolant Flush' },
    { value: 'timing_belt', label: t('serviceTypes.timingBelt') || 'Timing Belt' },
    { value: 'inspection', label: t('serviceTypes.inspection') || 'Inspection' },
    { value: 'full_service', label: t('serviceTypes.fullService') || 'Full Service' },
    { value: 'other', label: t('serviceTypes.other') || 'Other' },
  ]

  const selectedVehicleId = watch('vehicle_id')
  const selectedVehicle = vehicles.find(v => v.id === parseInt(selectedVehicleId))
  const distUnit = normalizeDistanceUnit(selectedVehicle?.distance_unit || user?.distance_unit) === 'miles' ? 'mi' : 'km'

  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('addService.title') || 'Add Service'}</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
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
        
        {/* Vehicle & Date */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('common.vehicle') || 'Vehicle'} *
            </label>
            <select 
              {...register('vehicle_id', { required: t('validation.selectVehicle') || 'Select a vehicle' })}
              className="input"
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
                {t('addService.date') || 'Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addService.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addService.odometer') || 'Odometer'} ({distUnit})
              </label>
              <input
                type="number"
                {...register('mileage', { min: 0 })}
                className="input"
                placeholder="0"
              />
            </div>
          </div>
        </div>
        
        {/* Service Details */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('addService.serviceDetails') || 'Service Details'}</h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.serviceType') || 'Service Type'} *
            </label>
            <p className="text-xs text-[var(--color-text-secondary)] mb-2">
              {t('addService.multiSelectHint') || 'Tap to select one or more service types'}
            </p>
            <div className="flex flex-wrap gap-2">
              {serviceTypes.map(type => {
                const isSelected = selectedServiceTypes.includes(type.value)
                return (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => {
                      setSelectedServiceTypes(prev =>
                        prev.includes(type.value)
                          ? prev.filter(v => v !== type.value)
                          : [...prev, type.value]
                      )
                    }}
                    className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-all ${
                      isSelected
                        ? 'bg-[var(--color-primary)] text-white border-[var(--color-primary)]'
                        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] border-[var(--color-border)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]'
                    }`}
                  >
                    {isSelected && (
                      <svg className="inline-block w-3.5 h-3.5 mr-1 -mt-0.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    )}
                    {type.label}
                  </button>
                )
              })}
            </div>
            {selectedServiceTypes.length === 0 && error && (
              <p className="text-xs text-red-500 mt-1">{t('addService.typeRequired') || 'Service type is required'}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.description') || 'Description'}
            </label>
            <input
              type="text"
              {...register('description')}
              className="input"
              placeholder={t('addService.descriptionPlaceholder') || 'What was done?'}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.shopName') || 'Service Shop'}
            </label>
            <input
              type="text"
              {...register('shop_name')}
              className="input"
              placeholder={t('addService.optional') || 'Where was it done?'}
            />
          </div>
        </div>
        
        {/* Costs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('addService.costs') || 'Costs'}</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addService.laborCost') || 'Labor Cost'}
              </label>
              <input
                type="number"
                step="0.01"
                {...register('labor_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addService.partsCost') || 'Parts Cost'}
              </label>
              <input
                type="number"
                step="0.01"
                {...register('parts_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.totalCost') || 'Total Cost'}
            </label>
            <input
              type="number"
              step="0.01"
              {...register('total_cost')}
              className="input"
              placeholder={t('addService.totalCostPlaceholder') || 'Auto-calculated or enter manually'}
            />
          </div>
        </div>
        
        {/* Notes */}
        <div className="card">
          <label className="block text-xs text-[var(--color-text-muted)] mb-1">
            {t('addService.notes') || 'Notes'}
          </label>
          <textarea
            {...register('notes')}
            className="input resize-none"
            rows={3}
            placeholder={t('addService.optionalNotes') || 'Additional details, part numbers, etc...'}
          />
        </div>
      </form>
    </div>
  )
}
