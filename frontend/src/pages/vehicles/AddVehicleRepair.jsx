import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm, useWatch } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { repairApi, vehicleApi, attachmentApi } from '../../services/api'
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
  const [selectedRepairTypes, setSelectedRepairTypes] = useState([])
  const [uploadedAttachmentId, setUploadedAttachmentId] = useState(null)
  const [ocrTypeHint, setOcrTypeHint] = useState(false)
  const _ocrTypeTimerRef = useRef(null)
  
  const { register, handleSubmit, formState: { errors, isDirty }, setValue, control, reset } = useForm({
    defaultValues: {
      date: new Date().toISOString().split('T')[0],
      mileage: '',
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
            description: entry.description || '',
            parts_cost: entry.parts_cost || '',
            labor_cost: entry.labor_cost || '',
            total_cost: entry.amount || '',
            shop_name: entry.garage_name || entry.provider || '',
            notes: entry.notes || '',
          })
          
          // Restore multi-select repair types
          if (entry.repair_types && entry.repair_types.length > 0) {
            setSelectedRepairTypes(entry.repair_types)
          } else if (entry.repair_type) {
            setSelectedRepairTypes([entry.repair_type])
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
  
  useUnsavedChanges(isDirty)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    // Additional frontend validation
    if (selectedRepairTypes.length === 0) {
      setError(t('addRepair.repairTypeRequired') || 'Repair type is required')
      setIsSubmitting(false)
      return
    }
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        repair_types: selectedRepairTypes,
        repair_type: selectedRepairTypes[0],
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
      
      // Link or upload receipt attachment
      const entryId = isEditMode ? editId : response.data?.entry?.id
      if (uploadedAttachmentId && entryId) {
        try {
          await attachmentApi.update(uploadedAttachmentId, { entry_id: entryId })
        } catch (linkErr) {
          console.error('Failed to link attachment:', linkErr)
        }
      } else if (receiptFile && entryId) {
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
                {t('addRepair.odometer') || 'Odometer'} ({distUnit})
              </label>
              <input
                type="number" inputMode="decimal"
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
            <p className="text-xs text-[var(--color-text-secondary)] mb-2">
              {t('addRepair.multiSelectHint') || 'Tap to select one or more repair types'}
            </p>
            <div className="flex flex-wrap gap-2">
              {repairTypes.map(type => {
                const isSelected = selectedRepairTypes.includes(type.value)
                return (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => {
                      setSelectedRepairTypes(prev =>
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
            {selectedRepairTypes.length === 0 && error && (
              <p className="text-xs text-red-500 mt-1">{t('addRepair.repairTypeRequired') || 'Repair type is required'}</p>
            )}
            {ocrTypeHint && (
              <p className="text-xs text-purple-400 mt-1.5 flex items-center gap-1">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
                  <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
                  <line x1="4" y1="12" x2="20" y2="12"/>
                </svg>
                {t('addRepair.ocrTypeHint') || 'Auto-selected from receipt'}
              </p>
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
                type="number" inputMode="decimal"
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
                type="number" inputMode="decimal"
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
              type="number" inputMode="decimal"
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
        
        {/* Receipt Upload + OCR Scan Banner */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={(f) => { setReceiptFile(f); setUploadedAttachmentId(null) }}
            onFileRemove={() => { setReceiptFile(null); setUploadedAttachmentId(null) }}
            label={t('receipt.repairReceipt') || 'Repair Receipt'}
            disabled={isSubmitting}
          />
          <ScanReceiptBanner
            receiptFile={receiptFile}
            vehicleId={parseInt(vehicleId)}
            onUploadComplete={(id) => setUploadedAttachmentId(id)}
            onPrefill={(data) => {
              if (data.date) setValue('date', data.date)
              if (data.amount != null) setValue('total_cost', String(data.amount))
              if (data.vendor) setValue('shop_name', data.vendor)
              if (data.line_items?.[0]?.description) setValue('description', data.line_items[0].description)
              // §7.5 — infer repair_type from OCR line items + category when none selected
              if (selectedRepairTypes.length === 0) {
                const haystack = [
                  data.line_items?.[0]?.description,
                  data.category,
                  ...(data.line_items || []).slice(0, 3).map(i => i.description),
                ].filter(Boolean).join(' ').toLowerCase()
                const match =
                  /\bengine\b|\bmotor\b/.test(haystack) ? 'engine' :
                  /\btransmission\b|\bgearbox\b|\bcutie.vitez/.test(haystack) ? 'transmission' :
                  /\bbrake|\bfran[ae]\b|\bfrein\b/.test(haystack) ? 'brakes' :
                  /suspension|amortizor|strut|shock.absorb/.test(haystack) ? 'suspension' :
                  /electric|wiring|cablag/.test(haystack) ? 'electrical' :
                  /exhaust|toba|muffler|catalytic|evacuare/.test(haystack) ? 'exhaust' :
                  /radiator|termostat/.test(haystack) ? 'cooling' :
                  /fuel.pump|injector|pompa.benzin|sistem.combustibil/.test(haystack) ? 'fuel_system' :
                  /steering|directie|rack/.test(haystack) ? 'steering' :
                  /\bbody\b|caroserie|paint|vopsea|dent|zgariat/.test(haystack) ? 'body' :
                  /interior|tapiterie|scaun|carpet|mocheta/.test(haystack) ? 'interior' :
                  /\bac\b|air.condition|climatiz|incalzire/.test(haystack) ? 'ac_heating' :
                  /tire|tyre|anvelop|wheel|janta/.test(haystack) ? 'tires_wheels' :
                  /\bclutch\b|ambreiaj/.test(haystack) ? 'clutch' :
                  /drivetrain|axle|differential|cardan/.test(haystack) ? 'drivetrain' :
                  /\bturbo\b|supercharg/.test(haystack) ? 'turbo' :
                  /timing.belt|timing.chain|curea.distribut/.test(haystack) ? 'timing_belt' :
                  null
                if (match) {
                  setSelectedRepairTypes([match])
                  clearTimeout(_ocrTypeTimerRef.current)
                  setOcrTypeHint(true)
                  _ocrTypeTimerRef.current = setTimeout(() => setOcrTypeHint(false), 5000)
                }
              }
            }}
          />
        </div>
      </form>
    </div>
  )
}
