import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { repairApi, vehicleApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { normalizeDistanceUnit } from '../../utils/fuelEconomy'

export default function AddRepair() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  const { t } = useTranslation()
  const { user } = useAuth()
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [selectedRepairTypes, setSelectedRepairTypes] = useState([])
  
  const { register, handleSubmit, setValue, watch, formState: { errors, isDirty } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      description: '',
      shop_name: '',
      labor_cost: '',
      parts_cost: '',
      total_cost: '',
      warranty_months: '',
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
  
  useUnsavedChanges(isDirty)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    if (selectedRepairTypes.length === 0) {
      setError(t('addRepair.repairTypeRequired') || 'Repair type is required')
      setIsSubmitting(false)
      return
    }
    
    try {
      await repairApi.create({
        ...data,
        vehicle_id: parseInt(data.vehicle_id),
        repair_types: selectedRepairTypes,
        repair_type: selectedRepairTypes[0],
        mileage: data.mileage ? parseInt(data.mileage) : null,
        labor_cost: data.labor_cost ? parseFloat(data.labor_cost) : 0,
        parts_cost: data.parts_cost ? parseFloat(data.parts_cost) : 0,
        total_cost: data.total_cost ? parseFloat(data.total_cost) : 
          (parseFloat(data.labor_cost || 0) + parseFloat(data.parts_cost || 0)),
        warranty_months: data.warranty_months ? parseInt(data.warranty_months) : null,
      })
      
      navigate(-1)
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add repair entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const repairCategories = [
    { value: 'engine', label: t('repairTypes.engine') || 'Engine' },
    { value: 'transmission', label: t('repairTypes.transmission') || 'Transmission' },
    { value: 'brakes', label: t('repairTypes.brakes') || 'Brakes' },
    { value: 'suspension', label: t('repairTypes.suspension') || 'Suspension' },
    { value: 'electrical', label: t('repairTypes.electrical') || 'Electrical' },
    { value: 'exhaust', label: t('repairTypes.exhaust') || 'Exhaust' },
    { value: 'cooling', label: t('repairTypes.cooling') || 'Cooling System' },
    { value: 'fuel_system', label: t('repairTypes.fuelSystem') || 'Fuel System' },
    { value: 'ac_heating', label: t('repairTypes.acHeating') || 'A/C & Heating' },
    { value: 'steering', label: t('repairTypes.steering') || 'Steering' },
    { value: 'body', label: t('repairTypes.body') || 'Body/Exterior' },
    { value: 'interior', label: t('repairTypes.interior') || 'Interior' },
    { value: 'tires_wheels', label: t('repairTypes.tiresWheels') || 'Tires & Wheels' },
    { value: 'clutch', label: t('repairTypes.clutch') || 'Clutch' },
    { value: 'drivetrain', label: t('repairTypes.drivetrain') || 'Drivetrain/Axle' },
    { value: 'windshield', label: t('repairTypes.windshield') || 'Windshield/Glass' },
    { value: 'lights', label: t('repairTypes.lights') || 'Lights/Indicators' },
    { value: 'oil_change', label: t('repairTypes.oilChange') || 'Oil Change' },
    { value: 'filters', label: t('repairTypes.filters') || 'Filters' },
    { value: 'battery', label: t('repairTypes.battery') || 'Battery' },
    { value: 'turbo', label: t('repairTypes.turbo') || 'Turbo/Supercharger' },
    { value: 'timing_belt', label: t('repairTypes.timingBelt') || 'Timing Belt/Chain' },
    { value: 'differential', label: t('repairTypes.differential') || 'Differential' },
    { value: 'other', label: t('repairTypes.other') || 'Other' },
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
        <h1 className="text-base font-semibold flex-1">Add Repair</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? (
            <span className="material-icons-outlined icon-sm animate-spin">sync</span>
          ) : (
            'Save'
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
              Vehicle *
            </label>
            <select 
              {...register('vehicle_id', { required: 'Select a vehicle' })}
              className="input"
            >
              <option value="">Select vehicle</option>
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
                Date *
              </label>
              <input
                type="date"
                {...register('date', { required: 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addRepair.odometer') || 'Odometer'} ({distUnit})
              </label>
              <input
                type="number" inputMode="decimal"
                {...register('mileage', { min: 0 })}
                className="input"
                placeholder="0"
              />
            </div>
          </div>
        </div>
        
        {/* Repair Details */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addRepair.title') || 'Repair Details'}
          </h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addRepair.repairType') || 'Category'} *
            </label>
            <p className="text-xs text-[var(--color-text-secondary)] mb-2">
              {t('addRepair.multiSelectHint') || 'Tap to select one or more repair types'}
            </p>
            <div className="flex flex-wrap gap-2">
              {repairCategories.map(cat => {
                const isSelected = selectedRepairTypes.includes(cat.value)
                return (
                  <button
                    key={cat.value}
                    type="button"
                    onClick={() => {
                      setSelectedRepairTypes(prev =>
                        prev.includes(cat.value)
                          ? prev.filter(v => v !== cat.value)
                          : [...prev, cat.value]
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
                    {cat.label}
                  </button>
                )
              })}
            </div>
            {selectedRepairTypes.length === 0 && error && (
              <p className="text-xs text-red-500 mt-1">{t('addRepair.repairTypeRequired') || 'Repair type is required'}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Description *
            </label>
            <input
              type="text"
              {...register('description', { required: 'Description is required' })}
              className="input"
              placeholder="What was repaired?"
            />
            {errors.description && (
              <p className="text-xs text-red-500 mt-1">{errors.description.message}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Repair Shop
            </label>
            <input
              type="text"
              {...register('shop_name')}
              className="input"
              placeholder="Where was it repaired?"
            />
          </div>
        </div>
        
        {/* Costs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">Costs</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Labor Cost
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('labor_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Parts Cost
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('parts_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Total Cost
            </label>
            <input
              type="number" inputMode="decimal"
              step="0.01"
              {...register('total_cost')}
              className="input"
              placeholder="Auto-calculated or enter manually"
            />
          </div>
        </div>
        
        {/* Warranty & Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Warranty (months)
            </label>
            <input
              type="number" inputMode="decimal"
              {...register('warranty_months', { min: 0 })}
              className="input"
              placeholder="Enter warranty period if applicable"
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Notes
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={3}
              placeholder="Additional details, part numbers, symptoms, etc..."
            />
          </div>
        </div>
      </form>
    </div>
  )
}
