import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { vehicleApi } from '../../services/api'
import { useLanguage } from '../../contexts/LanguageContext'

export default function AddVehicle() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [photoPreview, setPhotoPreview] = useState(null)
  const [photoFile, setPhotoFile] = useState(null)
  const [showDimensions, setShowDimensions] = useState(false)
  const [distanceUnit, setDistanceUnit] = useState('km')
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  
  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: {
      name: '',
      make: '',
      model: '',
      year: new Date().getFullYear(),
      license_plate: '',
      vin: '',
      fuel_type: 'petrol',
      current_mileage: '',
      tank_capacity: '',
      engine_cc: '',
      vehicle_height_cm: '',
      vehicle_width_cm: '',
      vehicle_weight_kg: '',
    }
  })
  
  const handlePhotoSelect = (e) => {
    const file = e.target.files[0]
    if (file) {
      setPhotoFile(file)
      const reader = new FileReader()
      reader.onloadend = () => {
        setPhotoPreview(reader.result)
      }
      reader.readAsDataURL(file)
    }
  }
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const response = await vehicleApi.create({
        ...data,
        year: parseInt(data.year),
        current_mileage: data.current_mileage ? parseInt(data.current_mileage) : 0,
        tank_capacity: data.tank_capacity ? parseFloat(data.tank_capacity) : null,
        engine_cc: data.engine_cc ? parseInt(data.engine_cc) : null,
        vehicle_height_cm: data.vehicle_height_cm ? parseInt(data.vehicle_height_cm) : null,
        vehicle_width_cm: data.vehicle_width_cm ? parseInt(data.vehicle_width_cm) : null,
        vehicle_weight_kg: data.vehicle_weight_kg ? parseInt(data.vehicle_weight_kg) : null,
        distance_unit: distanceUnit,
      })
      
      // Upload photo if selected
      if (photoFile && response.data.vehicle?.id) {
        try {
          await vehicleApi.uploadPhoto(response.data.vehicle.id, photoFile)
        } catch (photoErr) {
          console.error('Photo upload failed:', photoErr)
          // Continue anyway, vehicle was created
        }
      }
      
      navigate(`/vehicles/${response.data.vehicle?.id || response.data.id}`)
    } catch (err) {
      setError(err.response?.data?.error || t('vehicles.addFailed'))
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const fuelTypes = [
    { value: 'petrol', label: t('fuel.petrol') },
    { value: 'diesel', label: t('fuel.diesel') },
    { value: 'lpg', label: t('fuel.lpg') },
    { value: 'electric', label: t('fuel.electric') },
    { value: 'hybrid', label: t('fuel.hybrid') },
    { value: 'plugin_hybrid', label: t('fuel.pluginHybrid') },
  ]
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('vehicles.add')}</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? (
            <span className="material-icons-outlined icon-sm animate-spin">sync</span>
          ) : (
            t('common.save')
          )}
        </button>
      </div>
      
      <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}
        
        {/* Photo Upload */}
        <div className="card flex flex-col items-center py-6">
          {/* Hidden file inputs */}
          <input
            type="file"
            ref={fileInputRef}
            accept="image/*"
            onChange={handlePhotoSelect}
            className="hidden"
          />
          <input
            type="file"
            ref={cameraInputRef}
            accept="image/*"
            capture="environment"
            onChange={handlePhotoSelect}
            className="hidden"
          />
          
          {photoPreview ? (
            <div className="relative">
              <img
                src={photoPreview}
                alt="Vehicle preview"
                className="w-32 h-32 rounded-2xl object-cover"
              />
              <button
                type="button"
                onClick={() => {
                  setPhotoPreview(null)
                  setPhotoFile(null)
                  if (fileInputRef.current) fileInputRef.current.value = ''
                  if (cameraInputRef.current) cameraInputRef.current.value = ''
                }}
                className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-red-500 text-white flex items-center justify-center"
              >
                <span className="material-icons-outlined text-sm">close</span>
              </button>
            </div>
          ) : (
            <div className="w-24 h-24 rounded-2xl bg-[var(--color-bg-tertiary)] flex items-center justify-center mb-3">
              <span className="material-icons-outlined icon-xl text-[var(--color-text-muted)]">
                directions_car
              </span>
            </div>
          )}
          
          {/* Photo action buttons */}
          <div className="flex gap-2 mt-3">
            <button 
              type="button" 
              className="btn btn-ghost btn-sm flex items-center gap-1"
              onClick={() => cameraInputRef.current?.click()}
            >
              <span className="material-icons-outlined icon-sm">photo_camera</span>
              {t('vehicles.camera')}
            </button>
            <button 
              type="button" 
              className="btn btn-ghost btn-sm flex items-center gap-1"
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="material-icons-outlined icon-sm">photo_library</span>
              {t('vehicles.gallery')}
            </button>
          </div>
        </div>
        
        {/* Basic Info */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('vehicles.basicInfo')}</h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('vehicles.vehicleName')} *
            </label>
            <input
              type="text"
              {...register('name', { required: t('vehicles.nameRequired') })}
              className="input"
              placeholder={t('vehicles.vehicleNamePlaceholder')}
            />
            {errors.name && (
              <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.make')} *
              </label>
              <input
                type="text"
                {...register('make', { required: t('vehicles.makeRequired') })}
                className="input"
                placeholder={t('vehicles.makePlaceholder')}
              />
              {errors.make && (
                <p className="text-xs text-red-500 mt-1">{errors.make.message}</p>
              )}
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.model')} *
              </label>
              <input
                type="text"
                {...register('model', { required: t('vehicles.modelRequired') })}
                className="input"
                placeholder={t('vehicles.modelPlaceholder')}
              />
              {errors.model && (
                <p className="text-xs text-red-500 mt-1">{errors.model.message}</p>
              )}
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.year')}
              </label>
              <input
                type="number"
                {...register('year', { 
                  min: { value: 1900, message: t('vehicles.invalidYear') },
                  max: { value: new Date().getFullYear() + 1, message: t('vehicles.invalidYear') }
                })}
                className="input"
                placeholder="2024"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.licensePlate')}
              </label>
              <input
                type="text"
                {...register('license_plate')}
                className="input uppercase"
                placeholder={t('vehicles.licensePlatePlaceholder')}
              />
            </div>
          </div>
        </div>
        
        {/* Technical */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('vehicles.technical')}</h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('vehicles.fuelType')}
            </label>
            <select {...register('fuel_type')} className="input">
              {fuelTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>
          
          {/* Distance Unit Toggle */}
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('vehicles.distanceUnit') || 'Distance Unit'}
            </label>
            <div className="flex rounded-xl overflow-hidden border border-[var(--color-border)]">
              {['km', 'miles'].map(unit => (
                <button
                  key={unit}
                  type="button"
                  onClick={() => setDistanceUnit(unit)}
                  className={`flex-1 py-2 text-sm font-medium transition-colors ${
                    distanceUnit === unit
                      ? 'bg-[var(--color-accent)] text-white'
                      : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]'
                  }`}
                >
                  {unit === 'km' ? (t('vehicles.kilometres') || 'Kilometres') : (t('vehicles.miles') || 'Miles')}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.currentMileage')} ({distanceUnit === 'miles' ? (t('vehicles.miles') || 'miles') : 'km'})
              </label>
              <input
                type="number"
                {...register('current_mileage', { min: 0 })}
                className="input"
                placeholder="0"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.tankCapacity')}
              </label>
              <input
                type="number"
                step="0.1"
                {...register('tank_capacity', { min: 0 })}
                className="input"
                placeholder="50"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('vehicles.vinOptional')}
            </label>
            <input
              type="text"
              {...register('vin')}
              className="input uppercase"
              placeholder={t('vehicles.vinPlaceholder')}
              maxLength={17}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('vehicles.engineSize')}
            </label>
            <input
              type="number"
              {...register('engine_cc', { min: 0 })}
              className="input"
              placeholder={t('vehicles.engineSizePlaceholder')}
            />
          </div>
        </div>
        
        {/* Dimensions (Collapsible) */}
        <div className="card">
          <button
            type="button"
            onClick={() => setShowDimensions(!showDimensions)}
            className="w-full flex items-center justify-between py-1"
          >
            <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
              {t('vehicles.dimensionsOptional')}
            </h3>
            <span className={`material-icons-outlined icon-sm text-[var(--color-text-muted)] transition-transform ${showDimensions ? 'rotate-180' : ''}`}>
              expand_more
            </span>
          </button>
          
          {showDimensions && (
            <div className="space-y-4 mt-4 pt-4 border-t border-[var(--color-border)]">
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('vehicles.dimensionsHelp')}
              </p>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('vehicles.height')}
                  </label>
                  <input
                    type="number"
                    {...register('vehicle_height_cm', { min: 0 })}
                    className="input"
                    placeholder={t('vehicles.heightPlaceholder')}
                  />
                </div>
                
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('vehicles.width')}
                  </label>
                  <input
                    type="number"
                    {...register('vehicle_width_cm', { min: 0 })}
                    className="input"
                    placeholder={t('vehicles.widthPlaceholder')}
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('vehicles.weight')}
                </label>
                <input
                  type="number"
                  {...register('vehicle_weight_kg', { min: 0 })}
                  className="input"
                  placeholder={t('vehicles.weightPlaceholder')}
                />
              </div>
            </div>
          )}
        </div>
      </form>
    </div>
  )
}
