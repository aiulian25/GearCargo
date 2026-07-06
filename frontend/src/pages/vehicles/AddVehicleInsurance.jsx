import { useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useForm } from 'react-hook-form'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { insuranceApi, vehicleApi, attachmentApi } from '../../services/api'
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
  shield: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  calendar: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
  phone: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
    </svg>
  ),
}

export default function AddVehicleInsurance() {
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
  
  // Calculate default dates
  const today = new Date().toISOString().split('T')[0]
  const oneYearLater = new Date(new Date().setFullYear(new Date().getFullYear() + 1)).toISOString().split('T')[0]
  
  const { register, handleSubmit, formState: { errors, isDirty }, reset, watch } = useForm({
    defaultValues: {
      provider: '',
      policy_number: '',
      policy_type: 'comprehensive',
      premium: '',
      payment_frequency: 'annual',
      start_date: today,
      end_date: oneYearLater,
      coverage_amount: '',
      deductible: '',
      agent_name: '',
      agent_phone: '',
      agent_email: '',
      claims_phone: '',
      auto_renew: false,
      notes: '',
    }
  })
  
  const paymentFrequency = watch('payment_frequency')
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await vehicleApi.getById(vehicleId)
        setVehicle(response.data)
        
        // If edit mode, fetch the policy
        if (isEditMode) {
          const policyRes = await insuranceApi.get(editId)
          const policy = policyRes.data
          
          reset({
            provider: policy.provider || '',
            policy_number: policy.policy_number || '',
            policy_type: policy.policy_type || 'comprehensive',
            premium: policy.premium || '',
            payment_frequency: policy.payment_frequency || 'annual',
            start_date: policy.start_date ? policy.start_date.split('T')[0] : today,
            end_date: policy.end_date ? policy.end_date.split('T')[0] : oneYearLater,
            coverage_amount: policy.coverage_amount || '',
            deductible: policy.deductible || '',
            agent_name: policy.agent_name || '',
            agent_phone: policy.agent_phone || '',
            agent_email: policy.agent_email || '',
            claims_phone: policy.claims_phone || '',
            auto_renew: policy.auto_renew || false,
            notes: policy.notes || '',
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
  }, [vehicleId, editId, isEditMode, navigate, reset, today, oneYearLater])
  
  useUnsavedChanges(isDirty)

  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      const payload = {
        ...data,
        vehicle_id: parseInt(vehicleId),
        premium: parseFloat(data.premium),
        coverage_amount: data.coverage_amount ? parseFloat(data.coverage_amount) : null,
        deductible: data.deductible ? parseFloat(data.deductible) : null,
      }
      
      let response
      if (isEditMode) {
        response = await insuranceApi.update(editId, payload)
      } else {
        response = await insuranceApi.create(payload)
      }
      
      // Upload document if selected
      const policyId = isEditMode ? editId : response.data?.policy?.id
      if (receiptFile && policyId) {
        try {
          await attachmentApi.upload(receiptFile, {
            vehicleId: parseInt(vehicleId),
            entryId: policyId,
            category: 'insurance_document',
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
      setError(err.response?.data?.error || t('addInsurance.error') || 'Failed to add insurance policy')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const policyTypes = [
    { value: 'comprehensive', label: t('insuranceTypes.comprehensive') || 'Comprehensive (Full Coverage)' },
    { value: 'third_party', label: t('insuranceTypes.thirdParty') || 'Third Party Liability' },
    { value: 'collision', label: t('insuranceTypes.collision') || 'Collision' },
    { value: 'liability', label: t('insuranceTypes.liability') || 'Liability Only' },
    { value: 'casco', label: t('insuranceTypes.casco') || 'CASCO' },
    { value: 'rca', label: t('insuranceTypes.rca') || 'RCA (Mandatory)' },
    { value: 'other', label: t('insuranceTypes.other') || 'Other' },
  ]
  
  const paymentFrequencies = [
    { value: 'monthly', label: t('addInsurance.monthly') || 'Monthly' },
    { value: 'quarterly', label: t('addInsurance.quarterly') || 'Quarterly (every 3 months)' },
    { value: 'semi_annual', label: t('addInsurance.semiAnnual') || 'Semi-Annual (every 6 months)' },
    { value: 'annual', label: t('addInsurance.annual') || 'Annual (yearly)' },
    { value: 'one_time', label: t('addInsurance.oneTime') || 'One-Time Payment' },
  ]
  
  // Calculate total annual cost for display
  const getAnnualCost = () => {
    const premium = watch('premium')
    if (!premium) return null
    const amount = parseFloat(premium)
    switch (paymentFrequency) {
      case 'monthly': return amount * 12
      case 'quarterly': return amount * 4
      case 'semi_annual': return amount * 2
      case 'annual': 
      case 'one_time':
      default: return amount
    }
  }
  
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
            {isEditMode ? (t('common.edit') || 'Edit') + ' ' + (t('nav.insurance') || 'Insurance') : (t('addInsurance.title') || 'Add Insurance')}
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
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
            {Icons.shield}
          </div>
          <div className="flex-1">
            <p className="font-medium">{vehicle?.name}</p>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle?.make} {vehicle?.model} • {vehicle?.license_plate}
            </p>
          </div>
        </div>
        
        {/* Provider & Policy Details */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addInsurance.policyDetails') || 'Policy Details'}
          </h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addInsurance.provider') || 'Insurance Provider'} *
            </label>
            <input
              type="text"
              {...register('provider', { required: t('addInsurance.providerRequired') || 'Provider is required' })}
              className="input"
              placeholder={t('addInsurance.providerPlaceholder') || 'e.g., Allianz, GEICO, State Farm'}
            />
            {errors.provider && (
              <p className="text-xs text-red-500 mt-1">{errors.provider.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.policyNumber') || 'Policy Number'}
              </label>
              <input
                type="text"
                {...register('policy_number')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.policyType') || 'Policy Type'} *
              </label>
              <select 
                {...register('policy_type', { required: true })}
                className="input"
              >
                {policyTypes.map(type => (
                  <option key={type.value} value={type.value}>{type.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        
        {/* Premium & Payment */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">
            {t('addInsurance.costDetails') || 'Cost & Payment'}
          </h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.premium') || 'Premium'} ({currency.symbol}) *
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('premium', { 
                  required: t('addInsurance.premiumRequired') || 'Premium is required',
                  min: { value: 0.01, message: t('addInsurance.invalidAmount') || 'Invalid amount' }
                })}
                className="input"
                placeholder="0.00"
              />
              {errors.premium && (
                <p className="text-xs text-red-500 mt-1">{errors.premium.message}</p>
              )}
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.paymentFrequency') || 'Payment Frequency'}
              </label>
              <select
                {...register('payment_frequency')}
                className="input"
              >
                {paymentFrequencies.map(freq => (
                  <option key={freq.value} value={freq.value}>{freq.label}</option>
                ))}
              </select>
            </div>
          </div>
          
          {/* Annual cost summary */}
          {getAnnualCost() && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-3">
              <p className="text-xs text-emerald-600 dark:text-emerald-400">
                <strong>{t('addInsurance.annualCost') || 'Annual Cost'}:</strong> {currency.symbol}{getAnnualCost().toFixed(2)}
                {paymentFrequency === 'monthly' && ` (${currency.symbol}${watch('premium')}/month × 12)`}
                {paymentFrequency === 'quarterly' && ` (${currency.symbol}${watch('premium')}/quarter × 4)`}
                {paymentFrequency === 'semi_annual' && ` (${currency.symbol}${watch('premium')}/6 months × 2)`}
              </p>
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.coverageAmount') || 'Coverage Amount'} ({currency.symbol})
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('coverage_amount')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.deductible') || 'Deductible'} ({currency.symbol})
              </label>
              <input
                type="number" inputMode="decimal"
                step="0.01"
                {...register('deductible')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
          </div>
        </div>
        
        {/* Policy Period */}
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
              {Icons.calendar}
            </div>
            <div>
              <p className="font-medium text-sm">{t('addInsurance.policyPeriod') || 'Policy Period'}</p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('addInsurance.policyPeriodHint') || 'When does the coverage start and end?'}
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.startDate') || 'Start Date'} *
              </label>
              <input
                type="date"
                {...register('start_date', { required: true })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.endDate') || 'End Date'} *
              </label>
              <input
                type="date"
                {...register('end_date', { required: true })}
                className="input"
              />
            </div>
          </div>
          
          <div className="flex items-center justify-between pt-2 border-t border-[var(--color-border)]">
            <div>
              <p className="font-medium text-sm">{t('addInsurance.autoRenew') || 'Auto-Renew'}</p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('addInsurance.autoRenewHint') || 'Policy renews automatically'}
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                {...register('auto_renew')}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
            </label>
          </div>
        </div>
        
        {/* Agent Contact (Optional) */}
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center text-purple-500">
              {Icons.phone}
            </div>
            <div>
              <p className="font-medium text-sm">{t('addInsurance.agentContact') || 'Agent Contact'}</p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {t('addInsurance.agentContactHint') || 'Optional - for quick reference'}
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.agentName') || 'Agent Name'}
              </label>
              <input
                type="text"
                {...register('agent_name')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.agentPhone') || 'Agent Phone'}
              </label>
              <input
                type="tel"
                {...register('agent_phone')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.agentEmail') || 'Agent Email'}
              </label>
              <input
                type="email"
                {...register('agent_email')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                {t('addInsurance.claimsPhone') || 'Claims Phone'}
              </label>
              <input
                type="tel"
                {...register('claims_phone')}
                className="input"
                placeholder={t('addInsurance.optional') || 'Optional'}
              />
            </div>
          </div>
        </div>
        
        {/* Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              {t('addInsurance.notes') || 'Notes'}
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={2}
              placeholder={t('addInsurance.optionalNotes') || 'Optional notes...'}
            />
          </div>
        </div>
        
        {/* Document Upload */}
        <div className="card">
          <ReceiptUpload
            selectedFile={receiptFile}
            onFileSelect={setReceiptFile}
            onFileRemove={() => setReceiptFile(null)}
            label={t('addInsurance.document') || 'Policy Document'}
            disabled={isSubmitting}
          />
        </div>
      </form>
    </div>
  )
}
