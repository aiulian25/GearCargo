import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { reminderApi, vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
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
  bell: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
}

export default function AddVehicleReminder() {
  const { id: vehicleId } = useParams()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const isEditMode = !!editId
  const navigate = useNavigate()
  const { t } = useTranslation()
  
  const [vehicle, setVehicle] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [receiptFile, setReceiptFile] = useState(null)
  const [existingAttachments, setExistingAttachments] = useState([])
  
  const { register, handleSubmit, watch, formState: { errors, isDirty }, reset } = useForm({
    defaultValues: {
      title: '',
      reminder_type: '',
      due_date: '',
      due_mileage: '',
      repeat_interval: '',
      repeat_mileage: '',
      notes: '',
    }
  })
  
  const reminderType = watch('reminder_type')
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await reminderApi.get(editId)
          const entry = entryRes.data
          
          reset({
            title: entry.title || '',
            reminder_type: entry.reminder_type || '',
            due_date: entry.due_date ? entry.due_date.split('T')[0] : '',
            due_mileage: entry.due_mileage || '',
            repeat_interval: entry.repeat_interval || '',
            repeat_mileage: entry.repeat_mileage || '',
            notes: entry.notes || entry.description || '',
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
    
    // Generate title from reminder type if not custom
    let title = data.title
    if (!title || data.reminder_type !== 'custom') {
      const typeLabels = {
        'oil_change': t('reminderTypes.oilChange') || 'Oil Change',
        'tire_rotation': t('reminderTypes.tireRotation') || 'Tire Rotation',
        'brake_inspection': t('reminderTypes.brakeInspection') || 'Brake Inspection',
        'air_filter': t('reminderTypes.airFilter') || 'Air Filter',
        'timing_belt': t('reminderTypes.timingBelt') || 'Timing Belt',
        'mot_inspection': t('reminderTypes.motInspection') || 'MOT/Technical Inspection',
        'insurance': t('reminderTypes.insurance') || 'Insurance Renewal',
        'road_tax': t('reminderTypes.roadTax') || 'Road Tax',
        'service': t('reminderTypes.service') || 'Regular Service',
      }
      title = typeLabels[data.reminder_type] || data.reminder_type || 'Reminder'
    }
    
    try {
      const payload = {
        ...data,
        title,
        vehicle_id: parseInt(vehicleId),
        due_mileage: data.due_mileage ? parseInt(data.due_mileage) : null,
        repeat_mileage: data.repeat_mileage ? parseInt(data.repeat_mileage) : null,
      }
      
      let response
      if (isEditMode) {
        response = await reminderApi.update(editId, payload)
      } else {
        response = await reminderApi.create(payload)
      }
      
      // Upload document if selected (only for new entries or if new file selected)
      const entryId = isEditMode ? editId : response.data?.reminder?.id
      if (receiptFile && entryId) {
        try {
          await attachmentApi.upload(receiptFile, {
            vehicleId: parseInt(vehicleId),
            entryId: entryId,
            category: 'document',
          })
        } catch (uploadErr) {
          console.error('Failed to upload document:', uploadErr)
        }
      }
      
      navigate(`/vehicles/${vehicleId}`)
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        navigate(`/vehicles/${vehicleId}`)
        return
      }
      setError(err.response?.data?.error || t('addReminder.error') || 'Failed to add reminder')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const reminderTypes = [
    { value: 'oil_change', label: t('reminderTypes.oilChange') || 'Oil Change' },
    { value: 'tire_rotation', label: t('reminderTypes.tireRotation') || 'Tire Rotation' },
    { value: 'brake_inspection', label: t('reminderTypes.brakeInspection') || 'Brake Inspection' },
    { value: 'air_filter', label: t('reminderTypes.airFilter') || 'Air Filter' },
    { value: 'timing_belt', label: t('reminderTypes.timingBelt') || 'Timing Belt' },
    { value: 'mot_inspection', label: t('reminderTypes.motInspection') || 'MOT/Technical Inspection' },
    { value: 'insurance', label: t('reminderTypes.insurance') || 'Insurance Renewal' },
    { value: 'road_tax', label: t('reminderTypes.roadTax') || 'Road Tax' },
    { value: 'service', label: t('reminderTypes.service') || 'Regular Service' },
    { value: 'custom', label: t('reminderTypes.custom') || 'Custom' },
  ]
  
  const repeatIntervals = [
    { value: '', label: t('addReminder.noRepeat') || 'Does not repeat' },
    { value: '1_month', label: t('addReminder.everyMonth') || 'Every month' },
    { value: '3_months', label: t('addReminder.every3Months') || 'Every 3 months' },
    { value: '6_months', label: t('addReminder.every6Months') || 'Every 6 months' },
    { value: '1_year', label: t('addReminder.everyYear') || 'Every year' },
    { value: '2_years', label: t('addReminder.every2Years') || 'Every 2 years' },
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.reminders') || 'Reminder') : (t('addReminder.title') || 'Add Reminder')}
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
          <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center text-green-500">
            {Icons.bell}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
            </p>
          </div>
        </div>
        
        {/* Reminder Details */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addReminder.reminderType') || 'Reminder Type'} *
            </label>
            <select 
              {...register('reminder_type', { required: t('addReminder.typeRequired') || 'Reminder type is required' })}
              className="input"
            >
              <option value="">{t('addReminder.selectType') || 'Select reminder type'}</option>
              {reminderTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            {errors.reminder_type && (
              <p className="text-xs text-red-500 mt-1">{errors.reminder_type.message}</p>
            )}
          </div>
          
          {reminderType === 'custom' && (
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addReminder.customTitle') || 'Custom Title'} *
              </label>
              <input
                type="text"
                {...register('title', { 
                  required: reminderType === 'custom' ? (t('addReminder.titleRequired') || 'Title is required') : false
                })}
                className="input"
                placeholder={t('addReminder.titlePlaceholder') || 'Enter reminder title'}
              />
              {errors.title && (
                <p className="text-xs text-red-500 mt-1">{errors.title.message}</p>
              )}
            </div>
          )}
        </div>
        
        {/* Due Date/Mileage */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addReminder.dueWhen') || 'When is it due?'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addReminder.dueDate') || 'Due Date'}
              </label>
              <input
                type="date"
                {...register('due_date')}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addReminder.dueMileage') || 'Due Mileage'} ({distUnit})
              </label>
              <input
                type="number" inputMode="decimal"
                {...register('due_mileage')}
                className="input"
                placeholder={t('addReminder.orMileage') || 'Or at mileage'}
              />
            </div>
          </div>
          
          <p className="text-xs text-[var(--color-text-muted)]">
            {t('addReminder.dueHint') || 'Set either a date, mileage, or both. The reminder will trigger when either condition is met.'}
          </p>
        </div>
        
        {/* Repeat */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addReminder.repeat') || 'Repeat'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addReminder.repeatInterval') || 'Repeat Interval'}
              </label>
              <select {...register('repeat_interval')} className="input">
                {repeatIntervals.map(interval => (
                  <option key={interval.value} value={interval.value}>{interval.label}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addReminder.repeatMileage') || 'Repeat Every'} ({distUnit})
              </label>
              <input
                type="number" inputMode="decimal"
                {...register('repeat_mileage')}
                className="input"
                placeholder={t('addReminder.everyXKm') || 'e.g., 10000'}
              />
            </div>
          </div>
        </div>
        
        {/* Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addReminder.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addReminder.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Document Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('receipt.document') || 'Attachment / Document'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
