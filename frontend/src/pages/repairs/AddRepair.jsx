import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { repairApi, vehicleApi } from '../../services/api'

export default function AddRepair() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const preselectedVehicle = searchParams.get('vehicle')
  
  const [vehicles, setVehicles] = useState([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  
  const { register, handleSubmit, setValue, formState: { errors } } = useForm({
    defaultValues: {
      vehicle_id: preselectedVehicle || '',
      date: new Date().toISOString().split('T')[0],
      mileage: '',
      description: '',
      category: '',
      shop_name: '',
      labor_cost: '',
      parts_cost: '',
      total_cost: '',
      warranty_months: '',
      notes: '',
    }
  })
  
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
  
  const onSubmit = async (data) => {
    setIsSubmitting(true)
    setError('')
    
    try {
      await repairApi.create({
        ...data,
        vehicle_id: parseInt(data.vehicle_id),
        mileage: data.mileage ? parseInt(data.mileage) : null,
        labor_cost: data.labor_cost ? parseFloat(data.labor_cost) : 0,
        parts_cost: data.parts_cost ? parseFloat(data.parts_cost) : 0,
        total_cost: data.total_cost ? parseFloat(data.total_cost) : 
          (parseFloat(data.labor_cost || 0) + parseFloat(data.parts_cost || 0)),
        warranty_months: data.warranty_months ? parseInt(data.warranty_months) : null,
      })
      
      navigate(-1)
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to add repair entry')
    } finally {
      setIsSubmitting(false)
    }
  }
  
  const repairCategories = [
    { value: 'engine', label: 'Engine' },
    { value: 'transmission', label: 'Transmission' },
    { value: 'brakes', label: 'Brakes' },
    { value: 'suspension', label: 'Suspension' },
    { value: 'electrical', label: 'Electrical' },
    { value: 'exhaust', label: 'Exhaust' },
    { value: 'cooling', label: 'Cooling System' },
    { value: 'ac_heating', label: 'A/C & Heating' },
    { value: 'steering', label: 'Steering' },
    { value: 'body', label: 'Body/Exterior' },
    { value: 'interior', label: 'Interior' },
    { value: 'tires_wheels', label: 'Tires & Wheels' },
    { value: 'other', label: 'Other' },
  ]
  
  return (
    <div className="pb-4">
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="btn-icon">
          <span className="material-icons-outlined icon-md">close</span>
        </button>
        <h1 className="text-base font-semibold flex-1">Add Repair</h1>
        <button 
          onClick={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          className="btn btn-primary btn-sm"
        >
          {isSubmitting ? (
            <span className="material-icons-outlined icon-sm animate-spin">sync</span>
          ) : (
            'Save'
          )}
        </button>
      </div>
      
      <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-4 py-3 rounded-xl text-sm">
            {error}
          </div>
        )}
        
        {/* Vehicle & Date */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Vehicle *
            </label>
            <select 
              {...register('vehicle_id', { required: 'Select a vehicle' })}
              className="input"
            >
              <option value="">Select vehicle</option>
              {vehicles.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
            {errors.vehicle_id && (
              <p className="text-xs text-red-500 mt-1">{errors.vehicle_id.message}</p>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Date *
              </label>
              <input
                type="date"
                {...register('date', { required: 'Date is required' })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Odometer (km)
              </label>
              <input
                type="number"
                {...register('mileage', { min: 0 })}
                className="input"
                placeholder="0"
              />
            </div>
          </div>
        </div>
        
        {/* Repair Details */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">Repair Details</h3>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Category
            </label>
            <select {...register('category')} className="input">
              <option value="">Select category</option>
              {repairCategories.map(cat => (
                <option key={cat.value} value={cat.value}>{cat.label}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Description *
            </label>
            <input
              type="text"
              {...register('description', { required: 'Description is required' })}
              className="input"
              placeholder="What was repaired?"
            />
            {errors.description && (
              <p className="text-xs text-red-500 mt-1">{errors.description.message}</p>
            )}
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Repair Shop
            </label>
            <input
              type="text"
              {...register('shop_name')}
              className="input"
              placeholder="Where was it repaired?"
            />
          </div>
        </div>
        
        {/* Costs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-secondary)]">Costs</h3>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Labor Cost
              </label>
              <input
                type="number"
                step="0.01"
                {...register('labor_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
            
            <div>
              <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                Parts Cost
              </label>
              <input
                type="number"
                step="0.01"
                {...register('parts_cost', { min: 0 })}
                className="input"
                placeholder="0.00"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Total Cost
            </label>
            <input
              type="number"
              step="0.01"
              {...register('total_cost')}
              className="input"
              placeholder="Auto-calculated or enter manually"
            />
          </div>
        </div>
        
        {/* Warranty & Notes */}
        <div className="card space-y-4">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Warranty (months)
            </label>
            <input
              type="number"
              {...register('warranty_months', { min: 0 })}
              className="input"
              placeholder="Enter warranty period if applicable"
            />
          </div>
          
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">
              Notes
            </label>
            <textarea
              {...register('notes')}
              className="input resize-none"
              rows={3}
              placeholder="Additional details, part numbers, symptoms, etc..."
            />
          </div>
        </div>
      </form>
    </div>
  )
}
