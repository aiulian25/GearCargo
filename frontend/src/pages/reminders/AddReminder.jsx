import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { reminderApi, vehicleApi } from '../../services/api'
import { addDays, addMonths, format } from 'date-fns'
import { useTranslation } from '../../contexts/LanguageContext'

export default function AddReminder() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      title: '',
      type: 'custom',
      due_date: '',
      due_mileage: '',
      repeat_interval: '',
      repeat_mileage: '',
      notes: '',
      priority: 'medium',
    }
  })
  
  const reminderType = watch('type')
  
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
        due_mileage: data.due_mileage ? parseInt(data.due_mileage) : null,
        repeat_interval: data.repeat_interval || null,
        repeat_mileage: data.repeat_mileage ? parseInt(data.repeat_mileage) : null,
      })
      
      navigate(-1)
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add reminder')
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
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
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
        
        {/* Type Selection */}
        <div className="card">
          <label className="block text-xs text-[var(--color-text-muted)] mb-2">
            {t('reminders.reminderType')}
          </label>
          <div className="grid grid-cols-4 gap-2">
            {reminderTypes.map(type => (
              <label
                key={type.value}
                className={`flex flex-col items-center gap-1 p-2 rounded-lg border cursor-pointer transition-colors ${
                  reminderType === type.value
                    ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/10'
                    : 'border-[var(--color-border)]'
                }`}
              >
                <input
                  type="radio"
                  {...register('type')}
                  value={type.value}
                  className="sr-only"
                />
                <span className={`material-icons-outlined icon-sm ${
                  reminderType === type.value ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'
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
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('reminders.dueWhen')}</h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
                  onClick={() => setValue('due_date', qd.date)}
                  className="px-2 py-1 text-2xs bg-[var(--color-bg-tertiary)] rounded-md hover:bg-[var(--color-accent)]/10 hover:text-[var(--color-accent)]"
                >
                  {qd.label}
                </button>
              ))}
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('reminders.dueAtMileage')}
            </label>
            <input
              type="number"
              {...register('due_mileage')}
              className="input"
              placeholder={t('reminders.mileagePlaceholder')}
            />
            <p className="text-2xs text-[var(--color-text-muted)] mt-1">
              {t('reminders.mileageHint')}
            </p>
          </div>
        </div>
        
        {/* Repeat */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">{t('reminders.repeat')}</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('reminders.interval')}
              </label>
              <select {...register('repeat_interval')} className="input">
                <option value="">{t('reminders.dontRepeat')}</option>
                <option value="weekly">{t('reminders.weekly')}</option>
                <option value="monthly">{t('reminders.monthly')}</option>
                <option value="quarterly">{t('reminders.quarterly')}</option>
                <option value="biannually">{t('reminders.biannually')}</option>
                <option value="yearly">{t('reminders.yearly')}</option>
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('reminders.everyXKm')}
              </label>
              <input
                type="number"
                {...register('repeat_mileage')}
                className="input"
                placeholder="e.g., 15000"
              />
            </div>
          </div>
        </div>
        
        {/* Priority & Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
                      : 'border-[var(--color-border)]'
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
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
