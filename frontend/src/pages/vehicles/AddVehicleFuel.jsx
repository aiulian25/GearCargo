import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { fuelApi, vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { normalizeDistanceUnit } from '../../utils/fuelEconomy'
import ReceiptUpload from '../../components/ReceiptUpload'
import ScanReceiptBanner from '../../components/ui/ScanReceiptBanner'

// SVG Icons
const Icons = {
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  spinner: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  ),
  fuel: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17"/><path d="M15 22H3"/><path d="M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3"/>
      <rect x="6" y="6" width="6" height="5" rx="1"/>
    </svg>
  ),
}

export default function AddVehicleFuel() {
  const { id: vehicleId } = useParams()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const isEditMode = !!editId
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  
  const [vehicle, setVehicle] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [receiptFile, setReceiptFile] = useState(null)
  const [existingAttachments, setExistingAttachments] = useState([])
  const [uploadedAttachmentId, setUploadedAttachmentId] = useState(null)
  
  const { register, handleSubmit, watch, setValue, reset, formState: { errors } } = useForm({
    defaultValues: {
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
  
  // Auto-calculate total cost
  useEffect(() => {
    if (liters && pricePerLiter) {
      const total = (parseFloat(liters) * parseFloat(pricePerLiter)).toFixed(2)
      setValue('total_cost', total)
    }
  }, [liters, pricePerLiter, setValue])
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch vehicle
        const vehicleRes = await vehicleApi.getById(vehicleId)
        setVehicle(vehicleRes.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await fuelApi.get(editId)
          const entry = entryRes.data
          
          reset({
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            mileage: entry.odometer || '',
            liters: entry.liters || '',
            price_per_liter: entry.price_per_liter || '',
            total_cost: entry.total_price || '',
            is_full_tank: entry.full_tank ?? true,
            fuel_type: entry.fuel_type || '',
            station_name: entry.station || '',
            notes: entry.notes || '',
          })
          
          if (entry.attachments && entry.attachments.length > 0) {
          }
        } else {
          // Pre-fill mileage from current vehicle mileage for new entries
          if (vehicleRes.data.current_mileage) {
            setValue('mileage', vehicleRes.data.current_mileage)
          }
        }
      } catch (error) {
        console.error('Failed to fetch data:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [vehicleId, editId, isEditMode, navigate, setValue, reset])
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        mileage: parseInt(data.mileage),
        liters: parseFloat(data.liters),
        price_per_liter: parseFloat(data.price_per_liter),
        total_cost: parseFloat(data.total_cost),
      }
      
      let response
      if (isEditMode) {
        response = await fuelApi.update(editId, payload)
      } else {
        response = await fuelApi.create(payload)
      }
      
      // Link or upload receipt attachment
      const entryId = isEditMode ? editId : response.data?.entry?.id
      if (uploadedAttachmentId && entryId) {
        // File was already uploaded by ScanReceiptBanner — just link it to the entry
        try {
          await attachmentApi.update(uploadedAttachmentId, { entry_id: entryId })
        } catch (linkErr) {
          console.error('Failed to link attachment:', linkErr)
        }
      } else if (receiptFile && entryId) {
        // Normal flow: upload now
        try {
          await attachmentApi.upload(receiptFile, {
            vehicleId: parseInt(vehicleId),
            entryId: entryId,
            category: 'receipt',
          })
        } catch (uploadErr) {
          console.error('Failed to upload receipt:', uploadErr)
        }
      }
      
      navigate(`/vehicles/${vehicleId}`)
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

  const distUnit = normalizeDistanceUnit(vehicle?.distance_unit) === 'miles' ? 'mi' : 'km'
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-12 rounded-xl mb-4" />
        <div className="skeleton h-40 rounded-xl mb-4" />
        <div className="skeleton h-40 rounded-xl" />
      </div>
    )
  }
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          {Icons.close}
        </button>
        <div className="flex-1">
          <h1 className="text-base font-semibold">
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.fuel') || 'Fuel') : (t('addFuel.title') || 'Add Fuel')}
          </h1>
          <p className="text-xs text-[var(--color-text-secondary)]">{vehicle?.name}</p>
        </div>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? Icons.spinner : (t('common.save') || 'Save')}
        </button>
      </div>
      
      <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}
        
        {/* Vehicle Info */}
        <div className="card flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500">
            {Icons.fuel}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
            </p>
          </div>
        </div>
        
        {/* Date & Odometer */}
        <div className="card space-y-4">
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
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addFuel.fuelDetails') || 'Fuel Details'}
          </h3>
          
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
                {t('addFuel.pricePerLiter') || 'Price/Liter'} ({currency.symbol}) *
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
              {t('addFuel.totalCost') || 'Total Cost'} ({currency.symbol})
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
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addFuel.additional') || 'Additional'}
          </h3>
          
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
        
        {/* Receipt Upload + OCR Scan Banner */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={(f) => { setReceiptFile(f); setUploadedAttachmentId(null) }}
            onFileRemove={() => { setReceiptFile(null); setUploadedAttachmentId(null) }}
            label={t('receipt.fuelReceipt') || 'Fuel Receipt'}
            disabled={isSubmitting}
          />
          <ScanReceiptBanner
            receiptFile={receiptFile}
            vehicleId={parseInt(vehicleId)}
            onUploadComplete={(id) => setUploadedAttachmentId(id)}
            onPrefill={(data) => {
              if (data.date) setValue('date', data.date)
              if (data.amount != null) setValue('total_cost', String(data.amount))
              if (data.vendor) setValue('station_name', data.vendor)
            }}
          />
        </div>
      </form>
    </div>
  )
}
