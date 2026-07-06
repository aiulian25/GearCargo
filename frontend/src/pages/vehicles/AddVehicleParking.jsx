import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm, useWatch } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import api from '../../services/api'
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
  parking: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/>
    </svg>
  ),
  recurring: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 2.1l4 4-4 4"/>
      <path d="M3 12.2v-2a4 4 0 0 1 4-4h12.8"/>
      <path d="M7 21.9l-4-4 4-4"/>
      <path d="M21 11.8v2a4 4 0 0 1-4 4H4.2"/>
    </svg>
  ),
}

// Parking API (may need to be added to the backend)
const parkingApi = {
  create: (data) => api.post('/parking', data),
  get: (id) => api.get(`/parking/${id}`),
  update: (id, data) => api.put(`/parking/${id}`, data),
}

export default function AddVehicleParking() {
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
  
  const { register, handleSubmit, formState: { errors, isDirty }, control, reset } = useForm({
    defaultValues: {
      date: new Date().toISOString().split('T')[0],
      parking_type: '',
      location: '',
      amount: '',
      start_time: '',
      end_time: '',
      notes: '',
      recurring: false,
      recurrence_type: 'monthly',
      reminder_days: 7,
      permit_number: '',
      permit_expires: '',
    }
  })
  
  // Watch recurring and parking type
  const isRecurring = useWatch({ control, name: 'recurring' })
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await parkingApi.get(editId)
          const entry = entryRes.data
          
          reset({
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            parking_type: entry.parking_type || '',
            location: entry.location || '',
            amount: entry.amount || '',
            start_time: entry.start_time || '',
            end_time: entry.end_time || '',
            notes: entry.notes || '',
            recurring: entry.recurring || false,
            recurrence_type: entry.recurrence_type || 'monthly',
            reminder_days: entry.reminder_days || 7,
            permit_number: entry.permit_number || '',
            permit_expires: entry.permit_expires ? entry.permit_expires.split('T')[0] : '',
          })
          
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
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        amount: parseFloat(data.amount),
      }
      
      let response
      if (isEditMode) {
        response = await parkingApi.update(editId, payload)
      } else {
        response = await parkingApi.create(payload)
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
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        navigate(`/vehicles/${vehicleId}`)
        return
      }
      setError(err.response?.data?.error || t('addParking.error') || 'Failed to add parking entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const parkingTypes = [
    { value: 'street', label: t('parkingTypes.street') || 'Street Parking' },
    { value: 'garage', label: t('parkingTypes.garage') || 'Parking Garage' },
    { value: 'lot', label: t('parkingTypes.lot') || 'Parking Lot' },
    { value: 'monthly', label: t('parkingTypes.monthly') || 'Monthly Permit' },
    { value: 'airport', label: t('parkingTypes.airport') || 'Airport Parking' },
    { value: 'valet', label: t('parkingTypes.valet') || 'Valet' },
    { value: 'other', label: t('parkingTypes.other') || 'Other' },
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.parking') || 'Parking') : (t('addParking.title') || 'Add Parking')}
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
          <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500">
            {Icons.parking}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {vehicle?.license_plate}
            </p>
          </div>
        </div>
        
        {/* Parking Details */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addParking.parkingType') || 'Parking Type'} *
            </label>
            <select 
              {...register('parking_type', { required: t('addParking.typeRequired') || 'Parking type is required' })}
              className="input"
            >
              <option value="">{t('addParking.selectType') || 'Select parking type'}</option>
              {parkingTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            {errors.parking_type && (
              <p className="text-xs text-red-500 mt-1">{errors.parking_type.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addParking.date') || 'Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addParking.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addParking.amount') || 'Amount'} ({currency.symbol}) *
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('amount', { 
                  required: t('addParking.amountRequired') || 'Amount is required',
                  min: { value: 0.01, message: t('addParking.invalidAmount') || 'Invalid amount' }
                })}
                className="input"
                placeholder="0.00"
              />
              {errors.amount && (
                <p className="text-xs text-red-500 mt-1">{errors.amount.message}</p>
              )}
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addParking.location') || 'Location'}
            </label>
            <input
              type="text"
              {...register('location')}
              className="input"
              placeholder={t('addParking.locationPlaceholder') || 'Where did you park?'}
            />
          </div>
        </div>
        
        {/* Time */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addParking.duration') || 'Duration (Optional)'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addParking.startTime') || 'Start Time'}
              </label>
              <input
                type="time"
                {...register('start_time')}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addParking.endTime') || 'End Time'}
              </label>
              <input
                type="time"
                {...register('end_time')}
                className="input"
              />
            </div>
          </div>
        </div>
        
        {/* Recurring Option - for permits/subscriptions */}
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500">
                {Icons.recurring}
              </div>
              <div>
                <p className="font-medium text-sm">{t('recurring.parkingPermit') || 'Parking Permit/Subscription'}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('recurring.parkingDescription') || 'For monthly permits or recurring parking subscriptions'}
                </p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                {...register('recurring')}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-500"></div>
            </label>
          </div>
          
          {isRecurring && (
            <div className="space-y-4 pt-2 border-t border-[var(--color-border)]">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('recurring.permitNumber') || 'Permit Number'}
                  </label>
                  <input
                    type="text"
                    {...register('permit_number')}
                    className="input"
                    placeholder={t('addParking.optional') || 'Optional'}
                  />
                </div>
                
                <div>
                  <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                    {t('recurring.expiresOn') || 'Expires On'}
                  </label>
                  <input
                    type="date"
                    {...register('permit_expires')}
                    className="input"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('recurring.frequency') || 'Renewal Frequency'}
                </label>
                <select
                  {...register('recurrence_type')}
                  className="input"
                >
                  <option value="weekly">{t('recurring.weekly') || 'Weekly'}</option>
                  <option value="monthly">{t('recurring.monthly') || 'Monthly'}</option>
                  <option value="quarterly">{t('recurring.quarterly') || 'Quarterly (every 3 months)'}</option>
                  <option value="annual">{t('recurring.annual') || 'Annual (yearly)'}</option>
                </select>
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('recurring.reminderDays') || 'Remind me (days before expiry)'}
                </label>
                <select
                  {...register('reminder_days')}
                  className="input"
                >
                  <option value="3">{t('recurring.days3') || '3 days before'}</option>
                  <option value="7">{t('recurring.days7') || '7 days before'}</option>
                  <option value="14">{t('recurring.days14') || '14 days before'}</option>
                  <option value="30">{t('recurring.days30') || '30 days before'}</option>
                </select>
              </div>
              
              <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-3">
                <p className="text-xs text-purple-600 dark:text-purple-400">
                  <strong>{t('recurring.note') || 'Note'}:</strong> {t('recurring.parkingNote') || 'A reminder will be created to renew your parking permit before it expires.'}
                </p>
              </div>
            </div>
          )}
        </div>
        
        {/* Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addParking.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addParking.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Receipt Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('receipt.parkingReceipt') || 'Parking Receipt'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
