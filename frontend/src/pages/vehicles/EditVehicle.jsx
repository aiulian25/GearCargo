import { useState, useRef, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { vehicleApi } from '../../services/api'
import { useLanguage } from '../../contexts/LanguageContext'

export default function EditVehicle() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [photoPreview, setPhotoPreview] = useState(null)
  const [photoFile, setPhotoFile] = useState(null)
  const [photoChanged, setPhotoChanged] = useState(false)
  const [showDimensions, setShowDimensions] = useState(false)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  
  const { register, handleSubmit, formState: { errors }, reset } = useForm()
  
  // Load existing vehicle data
  useEffect(() => {
    const fetchVehicle = async () => {
      try {
        const response = await vehicleApi.getById(id)
        const vehicle = response.data
        
        // Reset form with existing values
        reset({
          name: vehicle.name || '',
          make: vehicle.make || '',
          model: vehicle.model || '',
          year: vehicle.year || new Date().getFullYear(),
          license_plate: vehicle.license_plate || '',
          vin: vehicle.vin || '',
          fuel_type: vehicle.fuel_type || 'petrol',
          current_mileage: vehicle.current_mileage || '',
          tank_capacity: vehicle.tank_capacity || '',
          engine_cc: vehicle.engine_cc || '',
          vehicle_height_cm: vehicle.vehicle_height_cm || '',
          vehicle_width_cm: vehicle.vehicle_width_cm || '',
          vehicle_weight_kg: vehicle.vehicle_weight_kg || '',
        })
        
        // Set existing photo if available
        if (vehicle.photo_url) {
          setPhotoPreview(vehicle.photo_url)
        }
        
        // Show dimensions section if any dimension is set
        if (vehicle.vehicle_height_cm || vehicle.vehicle_width_cm || vehicle.vehicle_weight_kg) {
          setShowDimensions(true)
        }
      } catch (err) {
        console.error('Failed to load vehicle:', err)
        setError(t('vehicles.loadFailed'))
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchVehicle()
  }, [id, reset, t])
  
  const handlePhotoSelect = (e) => {
    const file = e.target.files[0]
    if (file) {
      setPhotoFile(file)
      setPhotoChanged(true)
      const reader = new FileReader()
      reader.onloadend = () => {
        setPhotoPreview(reader.result)
      }
      reader.readAsDataURL(file)
    }
  }
  
  const handleRemovePhoto = () => {
    setPhotoPreview(null)
    setPhotoFile(null)
    setPhotoChanged(true)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (cameraInputRef.current) cameraInputRef.current.value = ''
  }
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      await vehicleApi.update(id, {
        ...data,
        year: parseInt(data.year),
        current_mileage: data.current_mileage ? parseInt(data.current_mileage) : 0,
        tank_capacity: data.tank_capacity ? parseFloat(data.tank_capacity) : null,
        engine_cc: data.engine_cc ? parseInt(data.engine_cc) : null,
        vehicle_height_cm: data.vehicle_height_cm ? parseInt(data.vehicle_height_cm) : null,
        vehicle_width_cm: data.vehicle_width_cm ? parseInt(data.vehicle_width_cm) : null,
        vehicle_weight_kg: data.vehicle_weight_kg ? parseInt(data.vehicle_weight_kg) : null,
      })
      
      // Handle photo changes
      if (photoChanged) {
        if (photoFile) {
          // Upload new photo
          try {
            await vehicleApi.uploadPhoto(id, photoFile)
          } catch (photoErr) {
            console.error('Photo upload failed:', photoErr)
          }
        } else {
          // Delete photo if removed
          try {
            await vehicleApi.deletePhoto(id)
          } catch (photoErr) {
            console.error('Photo delete failed:', photoErr)
          }
        }
      }
      
      navigate(`/vehicles/${id}`)
    } catch (err) {
      setError(err.response?.data?.error || t('vehicles.updateFailed'))
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
  
  if (isLoading) {
    return (
      <div className="pb-4">
        <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="btn-icon">
            <span className="material-icons-outlined icon-md">close</span>
          </button>
          <h1 className="text-base font-semibold flex-1">{t('vehicles.edit')}</h1>
        </div>
        <div className="p-4 space-y-4">
          <div className="card flex flex-col items-center py-6">
            <div className="skeleton w-24 h-24 rounded-2xl" />
          </div>
          <div className="card space-y-4">
            <div className="skeleton h-4 w-24 rounded" />
            <div className="skeleton h-10 rounded-xl" />
            <div className="grid grid-cols-2 gap-3">
              <div className="skeleton h-10 rounded-xl" />
              <div className="skeleton h-10 rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    )
  }
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('vehicles.edit')}</h1>
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
                onClick={handleRemovePhoto}
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
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('vehicles.currentMileage')} (km)
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
