import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm, useWatch } from 'react-hook-form'
import { serviceApi, vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { normalizeDistanceUnit } from '../../utils/fuelEconomy'
import ReceiptUpload from '../../components/ReceiptUpload'

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
  wrench: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
}

export default function AddVehicleService() {
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
  const [selectedServiceTypes, setSelectedServiceTypes] = useState([])
  
  const { register, handleSubmit, control, setValue, reset } = useForm({
    defaultValues: {
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      description: '',
      parts_cost: '',
      labor_cost: '',
      total_cost: '',
      shop_name: '',
      notes: '',
      next_due_date: '',
    }
  })
  
  // Watch parts_cost and labor_cost for auto-calculation
  const partsCost = useWatch({ control, name: 'parts_cost' })
  const laborCost = useWatch({ control, name: 'labor_cost' })
  
  // Auto-calculate total cost
  useEffect(() => {
    const parts = parseFloat(partsCost) || 0
    const labor = parseFloat(laborCost) || 0
    const total = parts + labor
    if (total > 0) {
      setValue('total_cost', total.toFixed(2))
    }
  }, [partsCost, laborCost, setValue])
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await serviceApi.get(editId)
          const entry = entryRes.data
          
          reset({
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            mileage: entry.odometer || '',
            description: entry.description || '',
            parts_cost: entry.parts_cost || '',
            labor_cost: entry.labor_cost || '',
            total_cost: entry.amount || '',
            shop_name: entry.garage_name || entry.provider || '',
            notes: entry.notes || '',
            next_due_date: entry.next_due_date ? entry.next_due_date.split('T')[0] : '',
          })
          
          // Restore multi-select service types
          if (entry.service_types && entry.service_types.length > 0) {
            setSelectedServiceTypes(entry.service_types)
          } else if (entry.service_type) {
            setSelectedServiceTypes([entry.service_type])
          }
          
          if (entry.attachments && entry.attachments.length > 0) {
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
  }, [vehicleId, editId, isEditMode, navigate, reset])
  
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
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        service_types: selectedServiceTypes,
        service_type: selectedServiceTypes[0],
        mileage: data.mileage ? parseInt(data.mileage) : null,
        parts_cost: data.parts_cost ? parseFloat(data.parts_cost) : null,
        labor_cost: data.labor_cost ? parseFloat(data.labor_cost) : null,
        total_cost: data.total_cost ? parseFloat(data.total_cost) : null,
        next_due_date: data.next_due_date || null,
      }
      
      let response
      if (isEditMode) {
        response = await serviceApi.update(editId, payload)
      } else {
        response = await serviceApi.create(payload)
      }
      
      // Upload receipt if selected (only for new entries or if new file selected)
      const entryId = isEditMode ? editId : response.data?.entry?.id
      if (receiptFile && entryId) {
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
    { value: 'transmission', label: t('serviceTypes.transmission') || 'Transmission Service' },
    { value: 'coolant', label: t('serviceTypes.coolant') || 'Coolant Flush' },
    { value: 'spark_plugs', label: t('serviceTypes.sparkPlugs') || 'Spark Plugs' },
    { value: 'timing_belt', label: t('serviceTypes.timingBelt') || 'Timing Belt' },
    { value: 'inspection', label: t('serviceTypes.inspection') || 'Inspection' },
    { value: 'full_service', label: t('serviceTypes.fullService') || 'Full Service' },
    { value: 'other', label: t('serviceTypes.other') || 'Other' },
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.service') || 'Service') : (t('addService.title') || 'Add Service')}
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
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
            {Icons.wrench}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
            </p>
          </div>
        </div>
        
        {/* Service Details */}
        <div className="card space-y-4">
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
                {...register('mileage')}
                className="input"
                placeholder="0"
              />
            </div>
          </div>
          
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
            <textarea
              {...register('description')}
              className="input resize-none"
              rows={2}
              placeholder={t('addService.descriptionPlaceholder') || 'What was done...'}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.nextServiceDue') || 'Next Service Due'}
            </label>
            <input
              type="date"
              {...register('next_due_date')}
              className="input"
            />
            <p className="text-2xs text-[var(--color-text-muted)] mt-1">
              {t('addService.nextServiceDueHint') || 'Optional - When should this service be done again?'}
            </p>
          </div>
        </div>
        
        {/* Costs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addService.costs') || 'Costs'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addService.partsCost') || 'Parts Cost'} ({currency.symbol})
              </label>
              <input
                type="number"
                step="0.01"
                {...register('parts_cost')}
                className="input"
                placeholder="0.00"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addService.laborCost') || 'Labor Cost'} ({currency.symbol})
              </label>
              <input
                type="number"
                step="0.01"
                {...register('labor_cost')}
                className="input"
                placeholder="0.00"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.totalCost') || 'Total Cost'} ({currency.symbol})
            </label>
            <input
              type="number"
              step="0.01"
              {...register('total_cost')}
              className="input"
              placeholder="0.00"
            />
          </div>
        </div>
        
        {/* Additional */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addService.additional') || 'Additional'}
          </h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.shopName') || 'Shop/Mechanic'}
            </label>
            <input
              type="text"
              {...register('shop_name')}
              className="input"
              placeholder={t('addService.optional') || 'Optional'}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addService.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addService.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Receipt Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('receipt.serviceReceipt') || 'Service Receipt'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
