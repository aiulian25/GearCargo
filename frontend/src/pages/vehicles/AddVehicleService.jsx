import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams, useSearchParams, useLocation } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm, useWatch } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { serviceApi, vehicleApi, attachmentApi } from '../../services/api'
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
  const [uploadedAttachmentId, setUploadedAttachmentId] = useState(null)
  const [ocrTypeHint, setOcrTypeHint] = useState(false)
  const _ocrTypeTimerRef = useRef(null)
  
  const { register, handleSubmit, control, setValue, reset, formState: { isDirty } } = useForm({
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
      warranty_months: '',
      warranty_km: '',
      warranty_expires: '',
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
            warranty_months: entry.warranty_months ?? '',
            warranty_km: entry.warranty_km ?? '',
            warranty_expires: entry.warranty_expires ? entry.warranty_expires.split('T')[0] : '',
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

  // F33 — receipt routed from ShareTarget: apply the AI-parsed fields and
  // adopt the already-uploaded attachment (linked to the entry after create).
  const location = useLocation()
  useEffect(() => {
    const st = location.state
    if (!st || isEditMode) return
    const d = st.prefill || {}
    if (d.date) setValue('date', d.date)
    if (d.amount != null) setValue('total_cost', String(d.amount))
    if (d.vendor) setValue('shop_name', d.vendor)
    if (d.line_items?.length) {
      setValue('notes', d.line_items.map(i => i.description).filter(Boolean).join(', '))
    }
    if (st.attachmentId) setUploadedAttachmentId(st.attachmentId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useUnsavedChanges(isDirty)

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
        warranty_months: data.warranty_months === '' ? null : parseInt(data.warranty_months),
        warranty_km: data.warranty_km === '' ? null : parseInt(data.warranty_km),
        warranty_expires: data.warranty_expires || null,
      }
      
      let response
      if (isEditMode) {
        response = await serviceApi.update(editId, payload)
      } else {
        response = await serviceApi.create(payload)
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
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        navigate(`/vehicles/${vehicleId}`)
        return
      }
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
                type="number" inputMode="decimal"
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
            {ocrTypeHint && (
              <p className="text-xs text-purple-400 mt-1.5 flex items-center gap-1">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
                  <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
                  <line x1="4" y1="12" x2="20" y2="12"/>
                </svg>
                {t('addService.ocrTypeHint') || 'Auto-selected from receipt'}
              </p>
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
                type="number" inputMode="decimal"
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
              {t('addService.totalCost') || 'Total Cost'} ({currency.symbol})
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

        {/* Warranty (F2) — feeds the "Under warranty" ledger in Vehicle Health */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('warranty.section') || 'Warranty'}
          </h3>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('warranty.months') || 'Warranty (months)'}
              </label>
              <input
                type="number" inputMode="numeric" min="0"
                {...register('warranty_months')}
                className="input"
                placeholder={t('addService.optional') || 'Optional'}
              />
            </div>

            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {(t('warranty.distance') || 'Warranty ({unit})').replace('{unit}', vehicle?.distance_unit || 'km')}
              </label>
              <input
                type="number" inputMode="numeric" min="0"
                {...register('warranty_km')}
                className="input"
                placeholder={t('addService.optional') || 'Optional'}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('warranty.expiresOn') || 'Warranty expires on'}
            </label>
            <input
              type="date"
              {...register('warranty_expires')}
              className="input"
            />
            <p className="text-2xs text-[var(--color-text-muted)] mt-1">
              {t('warranty.hint') || 'Optional — whichever limit is reached first ends the coverage.'}
            </p>
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
        
        {/* Receipt Upload + OCR Scan Banner */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={(f) => { setReceiptFile(f); setUploadedAttachmentId(null) }}
            onFileRemove={() => { setReceiptFile(null); setUploadedAttachmentId(null) }}
            label={t('receipt.serviceReceipt') || 'Service Receipt'}
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
              // §7.5 — infer service_type from OCR line items + category when none selected
              if (selectedServiceTypes.length === 0) {
                const haystack = [
                  data.line_items?.[0]?.description,
                  data.category,
                  ...(data.line_items || []).slice(0, 3).map(i => i.description),
                ].filter(Boolean).join(' ').toLowerCase()
                const match =
                  /oil.chang|engine.oil|synthetic.oil|schimb.ulei|cambio.aceit/.test(haystack) ? 'oil_change' :
                  /tire.rotat|tyre.rotat|rotati.anvelop|rotaci.neum/.test(haystack) ? 'tire_rotation' :
                  /\bbrake|\bfran[ae]\b|\bfrein\b/.test(haystack) ? 'brake_service' :
                  /air.filter|filtru.aer|filtro.aire/.test(haystack) ? 'air_filter' :
                  /cabin.filter|pollen.filter|filtru.cabin|filtro.habit/.test(haystack) ? 'cabin_filter' :
                  /\btransmission\b|\bcutie.vitez|\bcaja.cambio/.test(haystack) ? 'transmission' :
                  /coolant|antifreez|antigel|refrigerant/.test(haystack) ? 'coolant' :
                  /spark.plug|bujie|bujia/.test(haystack) ? 'spark_plugs' :
                  /timing.belt|timing.chain|curea.distribut|correa.distribuc/.test(haystack) ? 'timing_belt' :
                  /\binspect|\bitp\b|revision|revizie/.test(haystack) ? 'inspection' :
                  /full.service|service.complet|revizi.complet|servicio.complet/.test(haystack) ? 'full_service' :
                  null
                if (match) {
                  setSelectedServiceTypes([match])
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
