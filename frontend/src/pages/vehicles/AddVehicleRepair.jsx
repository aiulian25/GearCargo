import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm, useWatch } from 'react-hook-form'
import { repairApi, vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
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
  tools: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h4L17.5 10.5a2.121 2.121 0 0 0-3-3L4 18v3z"/><path d="M14.5 5.5l4 4"/>
    </svg>
  ),
}

export default function AddVehicleRepair() {
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
  
  const { register, handleSubmit, formState: { errors }, setValue, control, reset } = useForm({
    defaultValues: {
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      repair_type: '',
      description: '',
      parts_cost: '',
      labor_cost: '',
      total_cost: '',
      shop_name: '',
      notes: '',
    }
  })
  
  // Watch parts_cost and labor_cost for auto-calculation
  const partsCost = useWatch({ control, name: 'parts_cost' })
  const laborCost = useWatch({ control, name: 'labor_cost' })
  
  // Auto-calculate total cost
  useEffect(() => {
    const parts = parseFloat(partsCost) || 0
    const labor = parseFloat(laborCost) || 0
    if (parts > 0 || labor > 0) {
      setValue('total_cost', (parts + labor).toFixed(2))
    }
  }, [partsCost, laborCost, setValue])
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await repairApi.get(editId)
          const entry = entryRes.data
          
          reset({
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            mileage: entry.odometer || '',
            repair_type: entry.repair_type || '',
            description: entry.description || '',
            parts_cost: entry.parts_cost || '',
            labor_cost: entry.labor_cost || '',
            total_cost: entry.amount || '',
            shop_name: entry.garage_name || entry.provider || '',
            notes: entry.notes || '',
          })
          
          // Store existing attachments
          if (entry.attachments && entry.attachments.length > 0) {
            setExistingAttachments(entry.attachments)
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
    
    // Additional frontend validation
    if (!data.repair_type) {
      setError(t('addRepair.repairTypeRequired') || 'Repair type is required')
      setIsSubmitting(false)
      return
    }
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        mileage: data.mileage ? parseInt(data.mileage) : null,
        parts_cost: data.parts_cost ? parseFloat(data.parts_cost) : null,
        labor_cost: data.labor_cost ? parseFloat(data.labor_cost) : null,
        total_cost: data.total_cost ? parseFloat(data.total_cost) : null,
      }
      
      let response
      if (isEditMode) {
        response = await repairApi.update(editId, payload)
      } else {
        response = await repairApi.create(payload)
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
      // Translate known backend errors
      const backendError = err.response?.data?.error || ''
      if (backendError.toLowerCase().includes('repair type')) {
        setError(t('addRepair.repairTypeRequired') || 'Repair type is required')
      } else {
        setError(t('addRepair.error') || 'Failed to add repair entry')
      }
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const repairTypes = [
    { value: 'engine', label: t('repairTypes.engine') || 'Engine' },
    { value: 'transmission', label: t('repairTypes.transmission') || 'Transmission' },
    { value: 'brakes', label: t('repairTypes.brakes') || 'Brakes' },
    { value: 'suspension', label: t('repairTypes.suspension') || 'Suspension' },
    { value: 'electrical', label: t('repairTypes.electrical') || 'Electrical' },
    { value: 'exhaust', label: t('repairTypes.exhaust') || 'Exhaust' },
    { value: 'cooling', label: t('repairTypes.cooling') || 'Cooling System' },
    { value: 'fuel_system', label: t('repairTypes.fuelSystem') || 'Fuel System' },
    { value: 'steering', label: t('repairTypes.steering') || 'Steering' },
    { value: 'body', label: t('repairTypes.body') || 'Body/Paint' },
    { value: 'interior', label: t('repairTypes.interior') || 'Interior' },
    { value: 'ac_heating', label: t('repairTypes.acHeating') || 'A/C & Heating' },
    { value: 'tires_wheels', label: t('repairTypes.tiresWheels') || 'Tires & Wheels' },
    { value: 'other', label: t('repairTypes.other') || 'Other' },
  ]
  
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.repair') || 'Repair') : (t('addRepair.title') || 'Add Repair')}
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
          <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center text-red-500">
            {Icons.tools}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
            </p>
          </div>
        </div>
        
        {/* Repair Details */}
        <div className="card space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addRepair.date') || 'Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addRepair.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addRepair.odometer') || 'Odometer (km)'}
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
              {t('addRepair.repairType') || 'Repair Type'} *
            </label>
            <select
              {...register('repair_type', { required: t('addRepair.repairTypeRequired') || 'Repair type is required' })}
              className="input"
            >
              <option value="">{t('addRepair.selectType') || 'Select type...'}</option>
              {repairTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            {errors.repair_type && (
              <p className="text-xs text-red-500 mt-1">{errors.repair_type.message}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addRepair.description') || 'Description'} *
            </label>
            <textarea
              {...register('description', { required: t('addRepair.descRequired') || 'Description is required' })}
              className="input resize-none"
              rows={3}
              placeholder={t('addRepair.descPlaceholder') || 'What was repaired...'}
            />
            {errors.description && (
              <p className="text-xs text-red-500 mt-1">{errors.description.message}</p>
            )}
          </div>
        </div>
        
        {/* Costs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addRepair.costs') || 'Costs'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addRepair.partsCost') || 'Parts Cost'} ({currency.symbol})
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
                {t('addRepair.laborCost') || 'Labor Cost'} ({currency.symbol})
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
              {t('addRepair.totalCost') || 'Total Cost'} ({currency.symbol})
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
            {t('addRepair.additional') || 'Additional'}
          </h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addRepair.shopName') || 'Shop/Mechanic'}
            </label>
            <input
              type="text"
              {...register('shop_name')}
              className="input"
              placeholder={t('addRepair.optional') || 'Optional'}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addRepair.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addRepair.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Receipt Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('receipt.repairReceipt') || 'Repair Receipt'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
