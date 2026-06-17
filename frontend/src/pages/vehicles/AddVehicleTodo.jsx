import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
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
  create: (data) => api.post('/todos', data),
  get: (id) => api.get(`/todos/${id}`),
  update: (id, data) => api.put(`/todos/${id}`, data),
}

export default function AddVehicleTodo() {
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
  
  const { register, handleSubmit, formState: { errors, isDirty }, reset } = useForm({
    defaultValues: {
      title: '',
      description: '',
      priority: 'medium',
      due_date: '',
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
          
          reset({
            title: entry.title || '',
            description: entry.description || '',
            priority: entry.priority || 'medium',
            due_date: entry.due_date ? entry.due_date.split('T')[0] : '',
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
      }
      
      let response
      if (isEditMode) {
        response = await todoApi.update(editId, payload)
      } else {
        response = await todoApi.create(payload)
      }
      
      // Upload document if selected (only for new entries or if new file selected)
      const entryId = isEditMode ? editId : response.data?.todo?.id
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
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          {Icons.close}
        </button>
        <div className="flex-1">
          <h1 className="text-base font-semibold">
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.todos') || 'Todo') : (t('addTodo.title') || 'Add Todo')}
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
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center text-indigo-500">
            {Icons.checkSquare}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {vehicle?.license_plate}
            </p>
          </div>
        </div>
        
        {/* Todo Details */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
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
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTodo.priority') || 'Priority'}
              </label>
              <select {...register('priority')} className="input">
                {priorities.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTodo.dueDate') || 'Due Date'}
              </label>
              <input
                type="date"
                {...register('due_date')}
                className="input"
              />
            </div>
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
