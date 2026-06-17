import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { vehicleApi, consumableApi, attachmentApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import ReceiptUpload from '../../components/ReceiptUpload'

const Icons = {
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
  spinner: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  ),
}

// Consumable categories — labels resolved via i18n (consumableTypes.*)
const CONSUMABLE_TYPES = [
  'tire', 'battery', 'wipers', 'brake_pads', 'brake_discs',
  'air_filter', 'oil_filter', 'cabin_filter', 'fuel_filter',
  'coolant', 'spark_plugs', 'belt', 'other',
]

export default function AddVehicleConsumable() {
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

  const { register, handleSubmit, formState: { errors }, reset } = useForm({
    defaultValues: {
      consumable_type: 'tire',
      brand: '',
      date: new Date().toISOString().split('T')[0],
      odometer: '',
      amount: '',
      quantity: 1,
      expected_lifespan_km: '',
      expected_lifespan_months: '',
      warranty_months: '',
      notes: '',
    },
  })

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)

        if (isEditMode) {
          const entryRes = await consumableApi.get(editId)
          const entry = entryRes.data
          reset({
            consumable_type: entry.consumable_type || 'tire',
            brand: entry.brand || '',
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            odometer: entry.install_odometer ?? entry.odometer ?? '',
            amount: entry.amount || '',
            quantity: entry.quantity || 1,
            expected_lifespan_km: entry.expected_lifespan_km ?? '',
            expected_lifespan_months: entry.expected_lifespan_months ?? '',
            warranty_months: entry.warranty_months ?? '',
            notes: entry.notes || '',
          })
        } else if (response.data?.current_mileage) {
          // Pre-fill odometer with the vehicle's current reading for convenience.
          reset((prev) => ({ ...prev, odometer: response.data.current_mileage }))
        }
      } catch (err) {
        console.error('Failed to fetch data:', err)
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
    try {
      const payload = {
        vehicle_id: parseInt(vehicleId),
        consumable_type: data.consumable_type,
        brand: data.brand || null,
        date: data.date,
        install_date: data.date,
        odometer: data.odometer === '' ? null : parseInt(data.odometer),
        install_odometer: data.odometer === '' ? null : parseInt(data.odometer),
        amount: data.amount === '' ? 0 : parseFloat(data.amount),
        quantity: data.quantity === '' ? 1 : parseInt(data.quantity),
        expected_lifespan_km: data.expected_lifespan_km === '' ? null : parseInt(data.expected_lifespan_km),
        expected_lifespan_months: data.expected_lifespan_months === '' ? null : parseInt(data.expected_lifespan_months),
        warranty_months: data.warranty_months === '' ? null : parseInt(data.warranty_months),
        notes: data.notes || null,
      }

      let response
      if (isEditMode) {
        response = await consumableApi.update(editId, payload)
      } else {
        response = await consumableApi.create(payload)
      }

      const entryId = isEditMode ? editId : response.data?.entry?.id
      if (receiptFile && entryId) {
        try {
          await attachmentApi.upload(receiptFile, {
            vehicleId: parseInt(vehicleId),
            entryId,
            category: 'receipt',
          })
        } catch (uploadErr) {
          console.error('Failed to upload receipt:', uploadErr)
        }
      }

      navigate(`/vehicles/${vehicleId}/consumables`)
    } catch (err) {
      setError(err.response?.data?.error || t('addConsumable.error') || 'Failed to save consumable')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label={t('common.loading') || 'Loading...'}>
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    )
  }

  const distanceUnit = vehicle?.distance_unit === 'miles' ? (t('common.miles') || 'mi') : (t('common.km') || 'km')

  return (
    <div className="max-w-xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold">
          {isEditMode ? (t('addConsumable.editTitle') || 'Edit Consumable') : (t('addConsumable.title') || 'Add Consumable')}
        </h1>
        <button onClick={() => navigate(`/vehicles/${vehicleId}/consumables`)} className="btn-icon" aria-label={t('common.close') || 'Close'}>
          {Icons.close}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {/* Type */}
        <div>
          <label className="label" htmlFor="consumable_type">{t('addConsumable.type') || 'Type'}</label>
          <select id="consumable_type" className="input" {...register('consumable_type', { required: true })}>
            {CONSUMABLE_TYPES.map((typeKey) => (
              <option key={typeKey} value={typeKey}>
                {t(`consumableTypes.${typeKey}`) || typeKey}
              </option>
            ))}
          </select>
        </div>

        {/* Brand + Quantity */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="brand">{t('addConsumable.brand') || 'Brand'}</label>
            <input id="brand" type="text" className="input" placeholder={t('common.optional') || 'Optional'} {...register('brand')} />
          </div>
          <div>
            <label className="label" htmlFor="quantity">{t('addConsumable.quantity') || 'Quantity'}</label>
            <input id="quantity" type="number" inputMode="numeric" min="1" className="input" {...register('quantity')} />
          </div>
        </div>

        {/* Date + Cost */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="date">{t('addConsumable.installDate') || 'Install Date'}</label>
            <input id="date" type="date" className="input" {...register('date', { required: true })} />
          </div>
          <div>
            <label className="label" htmlFor="amount">{t('addConsumable.cost') || 'Cost'} ({currency.symbol})</label>
            <input id="amount" type="number" inputMode="decimal" step="0.01" min="0" className="input" placeholder="0.00" {...register('amount')} />
          </div>
        </div>

        {/* Odometer at install */}
        <div>
          <label className="label" htmlFor="odometer">
            {t('addConsumable.installOdometer') || 'Odometer at install'} ({distanceUnit})
          </label>
          <input id="odometer" type="number" inputMode="numeric" min="0" className="input" {...register('odometer')} />
        </div>

        {/* Expected lifespan — drives the wear estimate */}
        <fieldset className="border border-[var(--color-border)] rounded-xl p-3">
          <legend className="px-1 text-xs text-[var(--color-text-muted)]">{t('addConsumable.lifespanLegend') || 'Expected lifespan (for wear estimate)'}</legend>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="expected_lifespan_km">{t('addConsumable.lifespanKm') || 'Distance'} ({distanceUnit})</label>
              <input id="expected_lifespan_km" type="number" inputMode="numeric" min="0" className="input" placeholder={t('common.optional') || 'Optional'} {...register('expected_lifespan_km')} />
            </div>
            <div>
              <label className="label" htmlFor="expected_lifespan_months">{t('addConsumable.lifespanMonths') || 'Months'}</label>
              <input id="expected_lifespan_months" type="number" inputMode="numeric" min="0" className="input" placeholder={t('common.optional') || 'Optional'} {...register('expected_lifespan_months')} />
            </div>
          </div>
          <p className="text-2xs text-[var(--color-text-muted)] mt-2">
            {t('addConsumable.lifespanHint') || 'Set at least one to track wear. Whichever is reached first determines the estimate.'}
          </p>
        </fieldset>

        {/* Warranty */}
        <div>
          <label className="label" htmlFor="warranty_months">{t('addConsumable.warrantyMonths') || 'Warranty (months)'}</label>
          <input id="warranty_months" type="number" inputMode="numeric" min="0" className="input" placeholder={t('common.optional') || 'Optional'} {...register('warranty_months')} />
        </div>

        {/* Notes */}
        <div>
          <label className="label" htmlFor="notes">{t('common.notes') || 'Notes'}</label>
          <textarea id="notes" rows="2" className="input" placeholder={t('common.optional') || 'Optional'} {...register('notes')} />
        </div>

        {/* Receipt */}
        {!isEditMode && (
          <ReceiptUpload
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
          />
        )}

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full flex items-center justify-center gap-2">
          {isSubmitting && Icons.spinner}
          <span>{isEditMode ? (t('common.save') || 'Save') : (t('addConsumable.submit') || 'Add Consumable')}</span>
        </button>
      </form>
    </div>
  )
}
