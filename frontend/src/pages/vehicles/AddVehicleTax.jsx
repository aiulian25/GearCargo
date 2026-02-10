import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useForm, useWatch } from 'react-hook-form'
import { taxApi, vehicleApi, attachmentApi, insuranceApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
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
  receipt: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/>
      <path d="M16 8H8M16 12H8M10 16H8"/>
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
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
}

export default function AddVehicleTax() {
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
  const [insurancePolicies, setInsurancePolicies] = useState([])
  
  const { register, handleSubmit, formState: { errors }, control, reset } = useForm({
    defaultValues: {
      date: new Date().toISOString().split('T')[0],
      tax_type: '',
      amount: '',
      valid_from: new Date().toISOString().split('T')[0],
      valid_until: '',
      reference_number: '',
      notes: '',
      recurring: false,
      recurrence_type: 'annual',
      reminder_days: 30,
      insurance_policy_id: '',
    }
  })
  
  // Watch recurring toggle
  const isRecurring = useWatch({ control, name: 'recurring' })
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch vehicle and insurance policies in parallel
        const [vehicleRes, insuranceRes] = await Promise.all([
          vehicleApi.getById(vehicleId),
          insuranceApi.getAll(vehicleId)
        ])
        
        setVehicle(vehicleRes.data)
        setInsurancePolicies(insuranceRes.data?.policies || [])
        
        // If edit mode, fetch the entry
        if (isEditMode) {
          const entryRes = await taxApi.get(editId)
          const entry = entryRes.data
          
          reset({
            date: entry.date ? entry.date.split('T')[0] : new Date().toISOString().split('T')[0],
            tax_type: entry.tax_type || '',
            amount: entry.amount || '',
            valid_from: entry.valid_from ? entry.valid_from.split('T')[0] : '',
            valid_until: entry.valid_until ? entry.valid_until.split('T')[0] : '',
            reference_number: entry.reference_number || '',
            notes: entry.notes || '',
            recurring: entry.recurring || false,
            recurrence_type: entry.recurrence_type || 'annual',
            reminder_days: entry.reminder_days || 30,
            insurance_policy_id: entry.insurance_policy_id || '',
          })
          
          // Store existing attachments
          if (entry.attachments && entry.attachments.length > 0) {
            setExistingAttachments(entry.attachments)
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
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        amount: parseFloat(data.amount),
        insurance_policy_id: data.insurance_policy_id ? parseInt(data.insurance_policy_id) : null,
      }
      
      let response
      if (isEditMode) {
        response = await taxApi.update(editId, payload)
      } else {
        response = await taxApi.create(payload)
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
      setError(err.response?.data?.error || t('addTax.error') || 'Failed to add tax entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const taxTypes = [
    { value: 'road_tax', label: t('taxTypes.roadTax') || 'Road Tax' },
    { value: 'registration', label: t('taxTypes.registration') || 'Registration' },
    { value: 'inspection', label: t('taxTypes.inspection') || 'Technical Inspection (MOT/ITV)' },
    { value: 'emissions', label: t('taxTypes.emissions') || 'Emissions Test' },
    { value: 'toll', label: t('taxTypes.toll') || 'Toll/Vignette' },
    { value: 'other', label: t('taxTypes.other') || 'Other Tax/Fee' },
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('expenses.tax') || 'Tax') : (t('addTax.title') || 'Add Tax/Fee')}
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
          <div className="w-12 h-12 rounded-xl bg-rose-500/10 flex items-center justify-center text-rose-500">
            {Icons.receipt}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {vehicle?.license_plate}
            </p>
          </div>
        </div>
        
        {/* Tax Details */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addTax.taxType') || 'Tax Type'} *
            </label>
            <select 
              {...register('tax_type', { required: t('addTax.typeRequired') || 'Tax type is required' })}
              className="input"
            >
              <option value="">{t('addTax.selectType') || 'Select tax type'}</option>
              {taxTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            {errors.tax_type && (
              <p className="text-xs text-red-500 mt-1">{errors.tax_type.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTax.paymentDate') || 'Payment Date'} *
              </label>
              <input
                type="date"
                {...register('date', { required: t('addTax.dateRequired') || 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTax.amount') || 'Amount'} ({currency.symbol}) *
              </label>
              <input
                type="number"
                step="0.01"
                {...register('amount', { 
                  required: t('addTax.amountRequired') || 'Amount is required',
                  min: { value: 0.01, message: t('addTax.invalidAmount') || 'Invalid amount' }
                })}
                className="input"
                placeholder="0.00"
              />
              {errors.amount && (
                <p className="text-xs text-red-500 mt-1">{errors.amount.message}</p>
              )}
            </div>
          </div>
        </div>
        
        {/* Validity Period */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addTax.validityPeriod') || 'Validity Period'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTax.validFrom') || 'Valid From'}
              </label>
              <input
                type="date"
                {...register('valid_from')}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTax.validUntil') || 'Valid Until'}
              </label>
              <input
                type="date"
                {...register('valid_until')}
                className="input"
              />
            </div>
          </div>
        </div>
        
        {/* Linked Insurance Policy */}
        {insurancePolicies.length > 0 && (
          <div className="card space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                {Icons.shield}
              </div>
              <div className="flex-1">
                <p className="font-medium text-sm">{t('addTax.linkedInsurance') || 'Linked Insurance'}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('addTax.linkedInsuranceHint') || 'Link this tax to an insurance policy (optional)'}
                </p>
              </div>
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addTax.selectInsurance') || 'Select Insurance Policy'}
              </label>
              <select
                {...register('insurance_policy_id')}
                className="input"
              >
                <option value="">{t('addTax.noInsurance') || 'None'}</option>
                {insurancePolicies.map(policy => (
                  <option key={policy.id} value={policy.id}>
                    {policy.provider} - {policy.policy_type} ({policy.policy_number || t('common.noPolicyNumber') || 'No Policy #'})
                  </option>
                ))}
              </select>
            </div>
            
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-3">
              <p className="text-xs text-emerald-600 dark:text-emerald-400">
                {t('addTax.insuranceNote') || 'Linking to an insurance policy helps you track tax payments related to your coverage.'}
              </p>
            </div>
          </div>
        )}
        
        {/* Recurring Option */}
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
                {Icons.recurring}
              </div>
              <div>
                <p className="font-medium text-sm">{t('recurring.enableRecurring') || 'Recurring Payment'}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('recurring.taxDescription') || 'Automatically remind you when this tax is due again'}
                </p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                {...register('recurring')}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-500"></div>
            </label>
          </div>
          
          {isRecurring && (
            <div className="space-y-4 pt-2 border-t border-[var(--color-border)]">
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('recurring.frequency') || 'Frequency'}
                </label>
                <select
                  {...register('recurrence_type')}
                  className="input"
                >
                  <option value="monthly">{t('recurring.monthly') || 'Monthly'}</option>
                  <option value="quarterly">{t('recurring.quarterly') || 'Quarterly (every 3 months)'}</option>
                  <option value="semi_annual">{t('recurring.semiAnnual') || 'Semi-Annual (every 6 months)'}</option>
                  <option value="annual">{t('recurring.annual') || 'Annual (yearly)'}</option>
                </select>
              </div>
              
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('recurring.reminderDays') || 'Remind me (days before)'}
                </label>
                <select
                  {...register('reminder_days')}
                  className="input"
                >
                  <option value="7">{t('recurring.days7') || '7 days before'}</option>
                  <option value="14">{t('recurring.days14') || '14 days before'}</option>
                  <option value="30">{t('recurring.days30') || '30 days before'}</option>
                  <option value="60">{t('recurring.days60') || '60 days before'}</option>
                  <option value="90">{t('recurring.days90') || '90 days before'}</option>
                </select>
              </div>
              
              <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-3">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>{t('recurring.note') || 'Note'}:</strong> {t('recurring.taxNote') || 'A reminder will be created automatically based on the validity period and frequency you selected.'}
                </p>
              </div>
            </div>
          )}
        </div>
        
        {/* Additional */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addTax.additional') || 'Additional'}
          </h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addTax.referenceNumber') || 'Reference Number'}
            </label>
            <input
              type="text"
              {...register('reference_number')}
              className="input"
              placeholder={t('addTax.optional') || 'Optional'}
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addTax.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addTax.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Receipt Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('receipt.taxDocument') || 'Tax Document'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
