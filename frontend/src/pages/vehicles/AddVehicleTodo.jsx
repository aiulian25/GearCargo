import useExpenseNavigation from '../../hooks/useExpenseNavigation'
import { useMutationIntent } from '../../hooks/useMutationIntent'
import { useState, useEffect, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
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
  checkSquare: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
}

// Todo API (may need to be added to the backend)
const todoApi = {
  create: (data, config) => api.post('/todos', data, config),
  get: (id) => api.get(`/todos/${id}`),
  update: (id, data, config) => api.put(`/todos/${id}`, data, config),
}

export default function AddVehicleTodo() {
  const mutation = useMutationIntent()
  const savedEntry = useRef(null)
  const { id: vehicleId } = useParams()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const isEditMode = !!editId
  const navigate = useExpenseNavigation(vehicleId)
  const { t } = useTranslation()
  
  const [vehicle, setVehicle] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [receiptFile, setReceiptFile] = useState(null)
  const [existingAttachments, setExistingAttachments] = useState([])
  
  const { register, handleSubmit, formState: { errors, isDirty }, reset } = useForm({
    defaultValues: {
      title: '',
      description: '',
      priority: 'medium',
      due_date: '',
      repeat: '',   // F15: '' | weekly | monthly | yearly
    }
  })
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await todoApi.get(editId)
          const entry = entryRes.data
          mutation.capture(entry)
          
          reset({
            title: entry.title || '',
            description: entry.description || '',
            priority: entry.priority || 'medium',
            due_date: entry.due_date ? entry.due_date.split('T')[0] : '',
            repeat: entry.recurring ? (entry.frequency || '') : '',
          })
          
        }
      } catch (error) {
        console.error('Failed to fetch data:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [vehicleId, editId, isEditMode, navigate, reset, mutation])
  
  const markSaved = useUnsavedChanges(isDirty || receiptFile)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      // F15: map the single "Repeats" select onto the recurrence fields.
      const { repeat, ...rest } = data
      const payload = {
        ...rest,
        vehicle_id: parseInt(vehicleId),
        recurring: !!repeat,
        frequency: repeat || null,
        frequency_value: 1,
      }
      
      const targetId = editId || savedEntry.current?.id
      let response
      if (targetId) {
        response = await todoApi.update(targetId, payload, mutation.options())
      } else {
        response = await todoApi.create(payload, mutation.options())
      }
      
      // A document failure keeps the form open; retry against this saved parent.
      if (response.data?.todo) {
        savedEntry.current = response.data.todo
        mutation.capture(savedEntry.current)
      }

      // Upload document if selected (only for new entries or if new file selected)
      const entryId = targetId || savedEntry.current?.id
      if (receiptFile && entryId) {
        await attachmentApi.upload(receiptFile, {
          vehicleId: parseInt(vehicleId),
          entryId: entryId,
          category: 'document',
        })
      }
      
      if (!markSaved()) return
      navigate(`/vehicles/${vehicleId}`)
    } catch (err) {
      if (isOfflineWriteError(err)) {
        announceOfflineSaved(t)
        if (receiptFile) {
          setError(t('unsavedChanges.fileNotSaved'))
          return
        }
        if (!markSaved()) return
        navigate(`/vehicles/${vehicleId}`)
        return
      }
      setError(err.response?.data?.error || t('addTodo.error') || 'Failed to add todo')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const priorities = [
    { value: 'low', label: t('priorities.low') || 'Low', color: 'text-green-500' },
    { value: 'medium', label: t('priorities.medium') || 'Medium', color: 'text-amber-500' },
    { value: 'high', label: t('priorities.high') || 'High', color: 'text-red-500' },
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
      <div className="bg-(--color-bg-card) border-b border-(--color-border) px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          {Icons.close}
        </button>
        <div className="flex-1">
          <h1 className="text-base font-semibold">
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.todos') || 'Todo') : (t('addTodo.title') || 'Add Todo')}
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
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-500">
            {Icons.checkSquare}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-(--color-text-secondary)">
              {vehicle?.make} {vehicle?.model} • {vehicle?.license_plate}
            </p>
          </div>
        </div>
        
        {/* Todo Details */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('addTodo.taskTitle') || 'Task Title'} *
            </label>
            <input
              type="text"
              {...register('title', { required: t('addTodo.titleRequired') || 'Title is required' })}
              className="input"
              placeholder={t('addTodo.titlePlaceholder') || 'What needs to be done?'}
            />
            {errors.title && (
              <p className="text-xs text-red-500 mt-1">{errors.title.message}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('addTodo.description') || 'Description'}
            </label>
            <textarea
              {...register('description')}
              className="input resize-none"
              rows={3}
              placeholder={t('addTodo.descPlaceholder') || 'Add more details...'}
            />
          </div>
        </div>
        
        {/* Priority & Due Date */}
        <div className="card space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addTodo.priority') || 'Priority'}
              </label>
              <select {...register('priority')} className="input">
                {priorities.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-(--color-text-muted) mb-1">
                {t('addTodo.dueDate') || 'Due Date'}
              </label>
              <input
                type="date"
                {...register('due_date')}
                className="input"
              />
            </div>
          </div>

          {/* F15: Repeats — a recurring todo respawns its next occurrence on
              completion. Needs a due date to advance from. */}
          <div>
            <label className="block text-xs text-(--color-text-muted) mb-1">
              {t('todo.repeats') || 'Repeats'}
            </label>
            <select {...register('repeat')} className="input">
              <option value="">{t('addReminder.noRepeat') || 'Does not repeat'}</option>
              <option value="weekly">{t('recurring.weekly') || 'Weekly'}</option>
              <option value="monthly">{t('recurring.monthly') || 'Monthly'}</option>
              <option value="yearly">{t('recurring.annual') || 'Yearly'}</option>
            </select>
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
