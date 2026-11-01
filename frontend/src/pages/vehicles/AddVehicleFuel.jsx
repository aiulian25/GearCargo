import { localDate } from '../../utils/dateFormat'
import useExpenseNavigation from '../../hooks/useExpenseNavigation'
import { readPrivateNavigationState } from '../../utils/privateNavigation'
import toast from 'react-hot-toast'
import { saveExpenseWithReceipt } from '../../utils/receiptExpense'
import { useMutationIntent } from '../../hooks/useMutationIntent'
import { useState, useEffect, useRef } from 'react'
import { useParams, useSearchParams, useLocation } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { fuelApi, vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import {
  normalizeDistanceUnit, litersToDisplayVolume,
  pricePerLiterToDisplay, volumeUnitLabel, fuelFormPayload, editedFuelTotal,
} from '../../utils/fuelEconomy'
import ReceiptUpload from '../../components/ReceiptUpload'
import ScanReceiptBanner from '../../components/ui/ScanReceiptBanner'
import CurrencySelect from '../../components/ui/CurrencySelect'

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
  const mutation = useMutationIntent()
  const { id: vehicleId } = useParams()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const isEditMode = !!editId
  const navigate = useExpenseNavigation(vehicleId)
  const { t } = useTranslation()
  const { user } = useAuth()
  const { currency } = useCurrency()
  
  const initialValues = useRef(null)
  const originalEntry = useRef(null)
  const [vehicle, setVehicle] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [receiptFile, setReceiptFile] = useState(null)
  const [existingAttachments, setExistingAttachments] = useState([])
  const [uploadedAttachmentId, setUploadedAttachmentId] = useState(null)
  
  const { register, getValues, handleSubmit, watch, setValue, reset, formState: { errors, isDirty } } = useForm({
    defaultValues: {
      date: localDate(),
      mileage: '',
      liters: '',
      price_per_liter: '',
      total_cost: '',
      currency: user?.currency || 'EUR',
      is_full_tank: true,
      fuel_type: '',
      station_name: '',
      notes: '',
    }
  })
  
  const liters = watch('liters')
  const pricePerLiter = watch('price_per_liter')
  
  // Opening an edit must not replace stored totals with rounded display math.
  useEffect(() => {
    if (isEditMode && !initialValues.current) return
    const total = editedFuelTotal({ liters, price_per_liter: pricePerLiter }, user,
      initialValues.current, originalEntry.current)
    if (total != null) setValue('total_cost', total)
  }, [liters, pricePerLiter, setValue, isEditMode, user])

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
          mutation.capture(entry)
          
          originalEntry.current = entry
          const displayed = {
            date: entry.date ? entry.date.split('T')[0] : localDate(),
            mileage: entry.odometer ?? '',
            // F27 — stored litres shown in the user's volume unit.
            liters: entry.liters != null
              ? Math.round(litersToDisplayVolume(entry.liters, user) * 100) / 100 : '',
            price_per_liter: entry.price_per_liter != null
              ? Math.round(pricePerLiterToDisplay(entry.price_per_liter, user) * 1000) / 1000 : '',
            total_cost: entry.total_price ?? '',
            currency: entry.currency || user?.currency || 'EUR',
            is_full_tank: entry.full_tank ?? true,
            fuel_type: entry.fuel_type || '',
            station_name: entry.station || '',
            notes: entry.notes || '',
          }
          initialValues.current = displayed
          reset(displayed)
          
        } else {
          // Pre-fill mileage from current vehicle mileage for new entries
          if (vehicleRes.data.current_mileage) {
            setValue('mileage', vehicleRes.data.current_mileage)
          }
          // F48 — default the currency to the user's display currency once
          // auth has resolved (guards against a null user at useForm init).
          if (user?.currency) setValue('currency', user.currency)
        }
      } catch (error) {
        console.error('Failed to fetch data:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [vehicleId, editId, isEditMode, navigate, setValue, reset, mutation])

  // F33 — receipt routed from ShareTarget: apply the AI-parsed fields and
  // adopt the already-uploaded attachment (linked to the entry after create).
  const location = useLocation()
  useEffect(() => {
    const st = readPrivateNavigationState(location.state)
    if (!st || isEditMode) return
    const d = st.prefill || {}
    if (d.date) setValue('date', d.date, { shouldDirty: true })
    if (d.currency) setValue('currency', d.currency, { shouldDirty: true })
    if (d.amount != null) setValue('total_cost', String(d.amount), { shouldDirty: true })
    if (d.vendor) setValue('station_name', d.vendor, { shouldDirty: true })
    if (st.attachmentId) setUploadedAttachmentId(st.attachmentId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const markSaved = useUnsavedChanges(isDirty || receiptFile || uploadedAttachmentId)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const payload = {
        ...fuelFormPayload(data, user, isEditMode ? initialValues.current : null),
        vehicle_id: parseInt(vehicleId),
      }
      
      if (receiptFile || uploadedAttachmentId) {
        const result = await saveExpenseWithReceipt({ resource: 'fuel', editId,
          payload, config: mutation.options(), file: receiptFile, attachmentId: uploadedAttachmentId })
        if (result.receiptPending) toast(t('pwa.sync.receipts.savedPending'), { duration: 8000 })
      } else if (isEditMode) {
        await fuelApi.update(editId, payload, mutation.options())
      } else {
        await fuelApi.create(payload, mutation.options())
      }

      if (!markSaved()) return
      navigate(`/vehicles/${vehicleId}`)
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        if (!markSaved()) return
        navigate(`/vehicles/${vehicleId}`)
        return
      }
      // Prefer the server's message_key so the reason (malformed date,
      // non-numeric litres, price or odometer) is shown in the user's own language.
      const data = err.response?.data
      setError((data?.message_key && t(data.message_key))
        || data?.error
        || err.message
        || t('addFuel.error')
        || 'Failed to add fuel entry')
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

  const distUnit = vehicle?.distance_unit ? (normalizeDistanceUnit(vehicle.distance_unit) === 'miles' ? 'mi' : 'km') : t('units.unknown')
  
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
      <div className="bg-(--color-bg-card) border-b border-(--color-border) px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          {Icons.close}
        </button>
        <div className="flex-1">
          <h1 className="text-base font-semibold">
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.fuel') || 'Fuel') : (t('addFuel.title') || 'Add Fuel')}
          </h1>
          <p className="text-xs text-(--color-text-secondary)">{vehicle?.name}</p>
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
            <p className="text-xs text-(--color-text-secondary)">
              {vehicle?.make} {vehicle?.model} • {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
            </p>
          </div>
        </div>
        
        {/* Date & Odometer */}
        <div className="card space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addFuel.date') || 'Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addFuel.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addFuel.odometer') || 'Odometer'} ({distUnit}) *
              </label>
              <input
                type="number" inputMode="decimal"
                {...register('mileage', { 
                  required: !isEditMode && (t('addFuel.mileageRequired') || 'Mileage is required'),
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
          <h3 className="text-sm font-medium text-(--color-text-secondary)">
            {t('addFuel.fuelDetails') || 'Fuel Details'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {volumeUnitLabel(user, t)} *
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('liters', {
                  required: !isEditMode && (t('addFuel.litersRequired') || 'Liters is required'),
                  min: { value: 0, message: t('addFuel.invalidAmount') || 'Invalid amount' }
                })}
                className="input"
                placeholder="0.00"
              />
              {errors.liters && (
                <p className="text-xs text-red-500 mt-1">{errors.liters.message}</p>
              )}
            </div>
            
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addFuel.pricePerUnit', { unit: volumeUnitLabel(user, t) })} ({currency.symbol}) *
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.001"
                {...register('price_per_liter', { 
                  required: !isEditMode && (t('addFuel.priceRequired') || 'Price is required')
                })}
                className="input"
                placeholder="0.000"
              />
              {errors.price_per_liter && (
                <p className="text-xs text-red-500 mt-1">{errors.price_per_liter.message}</p>
              )}
            </div>
          </div>
          
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addFuel.totalCost') || 'Total Cost'} ({currency.symbol})
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('total_cost')}
                className="input bg-(--color-bg-tertiary)"
                placeholder={t('addFuel.calculatedAuto') || 'Calculated automatically'}
              />
            </div>
            <CurrencySelect extraCurrency={readPrivateNavigationState(location.state)?.prefill?.currency || getValues('currency')} register={register} className="w-28 shrink-0" />
          </div>
          
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="is_full_tank"
              {...register('is_full_tank')}
              className="w-5 h-5 rounded-sm border-(--color-border) text-(--color-accent) focus:ring-(--color-accent)"
            />
            <label htmlFor="is_full_tank" className="text-sm">
              {t('addFuel.fullTank') || 'Full tank fill-up'}
            </label>
          </div>
        </div>
        
        {/* Additional */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-(--color-text-secondary)">
            {t('addFuel.additional') || 'Additional'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addFuel.fuelType') || 'Fuel Type'}
              </label>
              <select {...register('fuel_type')} className="input">
                {fuelTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
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
            <label className="block text-xs text-(--color-text-muted) mb-1">
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
            durableDraft
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
