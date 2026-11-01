import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import ReminderDeliveryFields from '../../components/ReminderDeliveryFields'
import { useMutationIntent } from '../../hooks/useMutationIntent'
import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { reminderApi, vehicleApi } from '../../services/api'
import { addDays, addMonths, format } from 'date-fns'
import { useTranslation } from '../../contexts/LanguageContext'

export default function AddReminder() {
  const mutation = useMutationIntent()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  // AI Suggest state
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [aiSuggestions, setAiSuggestions] = useState([])
  
  const { register, handleSubmit, watch, setValue, formState: { errors, isDirty } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      title: '',
      type: 'custom',
      due_date: '',
      due_mileage: '',
      repeat_interval: '',
      repeat_mileage: '',
      notify_days_before: 7,
      notify_push: true,
      notify_email: true,
      notes: '',
      priority: 'medium',
    }
  })
  
  const reminderType = watch('type')
  const selectedVehicleId = watch('vehicle_id')

  // AI Suggest handler
  const handleAiSuggest = async () => {
    if (!selectedVehicleId) return
    setAiLoading(true)
    setAiError('')
    setAiSuggestions([])
    try {
      const locale = navigator.language || 'en-US'
      const resp = await vehicleApi.suggestReminder(selectedVehicleId, locale)
      setAiSuggestions(resp.data.suggestions || [])
    } catch (err) {
      if (err.response?.status === 429) {
        setAiError(t('reminders.aiRateLimited') || 'Too many AI requests. Please wait.')
      } else if (err.response?.status === 503) {
        setAiError(t('reminders.aiDisabled') || 'AI suggestions are not enabled.')
      } else {
        setAiError(t('reminders.aiError') || 'Could not load suggestions.')
      }
    } finally {
      setAiLoading(false)
    }
  }

  const applyAiSuggestion = (s) => {
    setValue('title', s.title, { shouldDirty: true })
    setValue('type', s.reminder_type, { shouldDirty: true })
    if (s.due_date) setValue('due_date', s.due_date, { shouldDirty: true })
    if (s.due_mileage) setValue('due_mileage', s.due_mileage, { shouldDirty: true })
    if (s.priority) setValue('priority', s.priority, { shouldDirty: true })
    if (s.repeat_interval) setValue('repeat_interval', s.repeat_interval, { shouldDirty: true })
    if (s.notes) setValue('notes', s.notes, { shouldDirty: true })
    setAiSuggestions([]) // collapse panel after selection
  }
  
  useEffect(() => {
    const fetchVehicles = async () => {
      try {
        const response = await vehicleApi.getAll()
        const vehicleList = response.data.vehicles || []
        setVehicles(vehicleList)
        
        if (vehicleList.length === 1 && !preselectedVehicle) {
          setValue('vehicle_id', vehicleList[0].id.toString())
        }
      } catch (error) {
        console.error('Failed to fetch vehicles:', error)
      }
    }
    
    fetchVehicles()
  }, [preselectedVehicle, setValue])
  
  // Auto-set title based on type
  useEffect(() => {
    const titles = {
      service: 'Scheduled Service',
      oil_change: 'Oil Change',
      insurance: 'Insurance Renewal',
      tax: 'Road Tax',
      inspection: 'Vehicle Inspection',
      tire_rotation: 'Tire Rotation',
      custom: '',
    }
    
    if (titles[reminderType] && !watch('title')) {
      setValue('title', titles[reminderType])
    }
  }, [reminderType, setValue, watch])
  
  const markSaved = useUnsavedChanges(isDirty)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    // Ensure title is always set
    let title = data.title
    if (!title) {
      const titles = {
        service: 'Scheduled Service',
        oil_change: 'Oil Change',
        insurance: 'Insurance Renewal',
        tax: 'Road Tax',
        inspection: 'Vehicle Inspection',
        tire_rotation: 'Tire Rotation',
        custom: 'Reminder',
      }
      title = titles[data.type] || data.type || 'Reminder'
    }
    
    try {
      await reminderApi.create({
        ...data,
        title,
        vehicle_id: parseInt(data.vehicle_id),
        due_mileage: data.due_mileage === '' || data.due_mileage == null ? null : Number(data.due_mileage),
        repeat_interval: data.repeat_interval || null,
        repeat_mileage: data.repeat_mileage ? parseInt(data.repeat_mileage) : null,
      }, mutation.options())
      
      if (!markSaved()) return
      navigate(-1)
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        if (!markSaved()) return
        navigate(-1)
        return
      }
      // Prefer the server's message_key so the reason (missing or malformed
      // due date, non-numeric mileage) is shown in the user's own language.
      const data = err.response?.data
      setError((data?.message_key && t(data.message_key))
        || data?.error
        || 'Failed to add reminder')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const quickDates = [
    { label: t('reminders.oneWeek'), date: format(addDays(new Date(), 7), 'yyyy-MM-dd') },
    { label: t('reminders.oneMonth'), date: format(addMonths(new Date(), 1), 'yyyy-MM-dd') },
    { label: t('reminders.threeMonths'), date: format(addMonths(new Date(), 3), 'yyyy-MM-dd') },
    { label: t('reminders.sixMonths'), date: format(addMonths(new Date(), 6), 'yyyy-MM-dd') },
    { label: t('reminders.oneYear'), date: format(addMonths(new Date(), 12), 'yyyy-MM-dd') },
  ]
  
  const reminderTypes = [
    { value: 'service', label: t('reminders.service'), icon: 'build' },
    { value: 'oil_change', label: t('reminders.oilChange'), icon: 'oil_barrel' },
    { value: 'insurance', label: t('reminders.insurance'), icon: 'shield' },
    { value: 'tax', label: t('reminders.roadTax'), icon: 'receipt_long' },
    { value: 'inspection', label: t('reminders.inspection'), icon: 'fact_check' },
    { value: 'tire_rotation', label: t('reminders.tireRotation'), icon: 'tire_repair' },
    { value: 'custom', label: t('reminders.custom'), icon: 'notifications' },
  ]
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-(--color-bg-card) border-b border-(--color-border) px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">{t('reminders.addReminder')}</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? (
            <span className="material-icons-outlined icon-sm animate-spin">sync</span>
          ) : (
            t('reminders.save')
          )}
        </button>
      </div>
      
      <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}

        {/* AI Suggest — only shown when a vehicle is selected and Ollama is available */}
        {selectedVehicleId && (
          <div className="card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-purple-400 text-base leading-none">✨</span>
                <span className="text-sm font-medium">{t('reminders.aiSuggest') || 'AI Suggest'}</span>
              </div>
              <button
                type="button"
                onClick={handleAiSuggest}
                disabled={aiLoading}
                className="btn btn-sm bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 border border-purple-500/20 flex items-center gap-1.5"
              >
                {aiLoading ? (
                  <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                  </svg>
                ) : (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14 2 9.27l6.91-1.01L12 2z"/>
                  </svg>
                )}
                {aiLoading
                  ? (t('reminders.aiSuggesting') || 'Suggesting…')
                  : (t('reminders.aiSuggest') || 'AI Suggest')}
              </button>
            </div>

            {aiError && (
              <p className="text-xs text-red-400 mt-2">{aiError}</p>
            )}

            {aiSuggestions.length > 0 && (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-(--color-text-muted)">
                  {t('reminders.aiSuggestions') || 'Suggestions — tap to pre-fill'}
                </p>
                {aiSuggestions.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => applyAiSuggestion(s)}
                    className="w-full text-left p-3 rounded-lg border border-purple-500/20 bg-purple-500/5 hover:bg-purple-500/10 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium text-(--color-text)">{s.title}</span>
                      <span className={`text-2xs px-1.5 py-0.5 rounded shrink-0 ${
                        s.priority === 'high'
                          ? 'bg-red-500/10 text-red-400'
                          : s.priority === 'medium'
                          ? 'bg-amber-500/10 text-amber-400'
                          : 'bg-green-500/10 text-green-400'
                      }`}>
                        {t(`reminders.${s.priority}`) || s.priority}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                      {s.due_date && (
                        <span className="text-2xs text-(--color-text-muted)">
                          📅 {s.due_date}
                        </span>
                      )}
                      {s.due_mileage && (
                        <span className="text-2xs text-(--color-text-muted)">
                          🏁 {s.due_mileage.toLocaleString()}
                        </span>
                      )}
                      {s.repeat_interval && (
                        <span className="text-2xs text-(--color-text-muted)">
                          🔁 {t(`reminders.${s.repeat_interval}`) || s.repeat_interval}
                        </span>
                      )}
                    </div>
                    {s.notes && (
                      <p className="text-2xs text-(--color-text-muted) mt-1 line-clamp-2">{s.notes}</p>
                    )}
                    <p className="text-2xs text-purple-400 mt-1.5 font-medium">
                      {t('reminders.useSuggestion') || 'Use this suggestion →'}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* Type Selection */}
        <div className="card">
          <label className="block text-xs text-(--color-text-muted) mb-2">
            {t('reminders.reminderType')}
          </label>
          <div className="grid grid-cols-4 gap-2">
            {reminderTypes.map(type => (
              <label
                key={type.value}
                className={`flex flex-col items-center gap-1 p-2 rounded-lg border cursor-pointer transition-colors ${
                  reminderType === type.value
                    ? 'border-(--color-accent) bg-(--color-accent)/10'
                    : 'border-(--color-border)'
                }`}
              >
                <input
                  type="radio"
                  {...register('type')}
                  value={type.value}
                  className="sr-only"
                />
                <span className={`material-icons-outlined icon-sm ${
                  reminderType === type.value ? 'text-(--color-accent)' : 'text-(--color-text-muted)'
                }`}>
                  {type.icon}
                </span>
                <span className="text-2xs text-center">{type.label}</span>
              </label>
            ))}
          </div>
        </div>
        
        {/* Basic Info */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.vehicle')} *
            </label>
            <select 
              {...register('vehicle_id', { required: t('reminders.selectVehicleRequired') })}
              className="input"
            >
              <option value="">{t('reminders.selectVehicle')}</option>
              {vehicles.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            {errors.vehicle_id && (
              <p className="text-xs text-red-500 mt-1">{errors.vehicle_id.message}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.titleLabel')} *
            </label>
            <input
              type="text"
              {...register('title', { required: t('reminders.titleRequired') })}
              className="input"
              placeholder={t('reminders.titlePlaceholder')}
            />
            {errors.title && (
              <p className="text-xs text-red-500 mt-1">{errors.title.message}</p>
            )}
          </div>
        </div>
        
        {/* Due Date */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-(--color-text-secondary)">{t('reminders.dueWhen')}</h3>
          
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.dueDateLabel')}
            </label>
            <input
              type="date"
              {...register('due_date')}
              className="input"
            />
            
            {/* Quick dates */}
            <div className="flex flex-wrap gap-2 mt-2">
              {quickDates.map(qd => (
                <button
                  key={qd.label}
                  type="button"
                  onClick={() => setValue('due_date', qd.date, { shouldDirty: true })}
                  className="px-2 py-1 text-2xs bg-(--color-bg-tertiary) rounded-md hover:bg-(--color-accent)/10 hover:text-(--color-accent)"
                >
                  {qd.label}
                </button>
              ))}
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.dueAtMileage')}
            </label>
            <input
              type="number" inputMode="decimal"
              {...register('due_mileage')}
              className="input"
              placeholder={t('reminders.mileagePlaceholder')}
            />
            <p className="text-2xs text-(--color-text-muted) mt-1">
              {t('reminders.mileageHint')}
            </p>
          </div>
        </div>
        
        {/* Repeat */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-(--color-text-secondary)">{t('reminders.repeat')}</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('reminders.interval')}
              </label>
              <select {...register('repeat_interval', { onChange: event => { if (!event.target.value) setValue('repeat_mileage', '') } })} className="input">
                <option value="">{t('reminders.dontRepeat')}</option>
                <option value="weekly">{t('reminders.weekly')}</option>
                <option value="monthly">{t('reminders.monthly')}</option>
                <option value="quarterly">{t('reminders.quarterly')}</option>
                <option value="biannually">{t('reminders.biannually')}</option>
                <option value="yearly">{t('reminders.yearly')}</option>
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('reminders.everyXKm')}
              </label>
              <input
                type="number" inputMode="decimal"
                {...register('repeat_mileage', { min: { value: 1, message: t('validation.invalidNumber') },
                  validate: value => !value || (watch('repeat_interval') && watch('due_mileage') !== '') || t('reminderDelivery.intervalRequired') })}
                className="input"
                placeholder="e.g., 15000"
              />
            </div>
          </div>
        </div>
        
        {errors.repeat_mileage && <p role="alert" className="text-sm text-red-500">{errors.repeat_mileage.message}</p>}
        <p className="text-xs text-(--color-text-muted)">{t('reminderDelivery.mileageHint')}</p>
        <ReminderDeliveryFields register={register} errors={errors} />

        {/* Priority & Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.priority')}
            </label>
            <div className="flex gap-2">
              {['low', 'medium', 'high'].map(p => (
                <label
                  key={p}
                  className={`flex-1 text-center py-2 rounded-lg border cursor-pointer text-xs font-medium capitalize ${
                    watch('priority') === p
                      ? p === 'high' 
                        ? 'border-red-500 bg-red-500/10 text-red-500'
                        : p === 'medium'
                        ? 'border-amber-500 bg-amber-500/10 text-amber-500'
                        : 'border-green-500 bg-green-500/10 text-green-500'
                      : 'border-(--color-border)'
                  }`}
                >
                  <input
                    type="radio"
                    {...register('priority')}
                    value={p}
                    className="sr-only"
                  />
                  {t(`reminders.${p}`)}
                </label>
              ))}
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('reminders.notes')}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('reminders.notesPlaceholder')}
            />
          </div>
        </div>
      </form>
    </div>
  )
}
