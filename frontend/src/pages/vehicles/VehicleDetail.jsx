import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { vehicleApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { formatDate } from '../../utils/dateFormat'
import { formatFuelEconomy } from '../../utils/fuelEconomy'

// SVG Icons
const Icons = {
  arrowBack: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 19l-7-7 7-7"/>
    </svg>
  ),
  moreVert: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
    </svg>
  ),
  edit: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  archive: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>
    </svg>
  ),
  delete: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>
  ),
  car: (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 16H9m10 0h3v-3.15a1 1 0 0 0-.84-.99L16 11l-2.7-3.6a1 1 0 0 0-.8-.4H5.24a2 2 0 0 0-1.8 1.1l-.8 1.63A6 6 0 0 0 2 12.42V16h2"/>
      <circle cx="6.5" cy="16.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>
    </svg>
  ),
  wallet: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>
    </svg>
  ),
  calendar: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  ),
  parking: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/>
    </svg>
  ),
  fuel: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 22V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v17"/><path d="M15 22H3"/><path d="M15 11h3a2 2 0 0 1 2 2v4a2 2 0 0 0 4 0V8l-4-3"/>
      <rect x="6" y="6" width="6" height="5" rx="1"/>
    </svg>
  ),
  speedometer: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M12 6v2"/><path d="M16.24 7.76l-1.42 1.42"/><path d="M18 12h-2"/><path d="M12 18v-6"/><circle cx="12" cy="12" r="2"/>
    </svg>
  ),
  wrench: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  ),
  receipt: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1z"/>
      <path d="M16 8H8M16 12H8M10 16H8"/>
    </svg>
  ),
  gauge: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z"/><path d="M12 14l3.5-3.5"/><circle cx="12" cy="14" r="1"/>
    </svg>
  ),
  clock: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  tools: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 21h4L17.5 10.5a2.121 2.121 0 0 0-3-3L4 18v3z"/><path d="M14.5 5.5l4 4"/>
      <path d="M12 8L7 3 3 7l5 5"/>
    </svg>
  ),
  search: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  expenses: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  ),
  timeline: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>
    </svg>
  ),
  chart: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/>
    </svg>
  ),
  alert: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
  plus: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  ),
  bell: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  shield: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  checkSquare: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
  heart: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>
    </svg>
  ),
  bookOpen: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
    </svg>
  ),
}

export default function VehicleDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { currency } = useCurrency()
  const { user } = useAuth()
  const [vehicle, setVehicle] = useState(null)
  const [stats, setStats] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [showMenu, setShowMenu] = useState(false)
  
  // Mileage update modal state
  const [showMileageModal, setShowMileageModal] = useState(false)
  const [newMileage, setNewMileage] = useState('')
  const [mileageError, setMileageError] = useState('')
  const [isSavingMileage, setIsSavingMileage] = useState(false)
  
  // Manual lookup state
  const [manualLoading, setManualLoading] = useState(false)
  const [manualResult, setManualResult] = useState(null)
  const [showManualModal, setShowManualModal] = useState(false)
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [vehicleRes, statsRes, timelineRes] = await Promise.all([
          vehicleApi.getById(id),
          vehicleApi.getStats(id),
          vehicleApi.getTimeline(id)
        ])
        setVehicle(vehicleRes.data)
        setStats(statsRes.data)
        setTimeline(timelineRes.data?.entries || [])
      } catch (error) {
        console.error('Failed to fetch vehicle:', error)
        navigate('/vehicles')
      } finally {
        setIsLoading(false)
      }
    }
    
    fetchData()
  }, [id, navigate])
  
  const handleDelete = async () => {
    if (window.confirm(t('vehicleDetail.deleteConfirm') || 'Delete this vehicle and all its data?')) {
      try {
        await vehicleApi.delete(id)
        navigate('/vehicles')
      } catch (error) {
        console.error('Failed to delete:', error)
      }
    }
  }
  
  const handleArchive = async () => {
    const confirmMessage = vehicle.archived 
      ? (t('archive.restoreConfirm') || 'Restore this vehicle from archive?')
      : (t('archive.archiveConfirm') || 'Archive this vehicle? It will be hidden from your dashboard.')
    
    if (window.confirm(confirmMessage)) {
      try {
        if (vehicle.archived) {
          await vehicleApi.unarchive(id)
          navigate('/') // Go to dashboard after restoring
        } else {
          await vehicleApi.archive(id)
          navigate('/') // Go to dashboard after archiving
        }
      } catch (error) {
        console.error('Failed to archive/unarchive:', error)
      }
    }
  }
  
  const handleOpenMileageModal = () => {
    setNewMileage(vehicle?.current_mileage?.toString() || '0')
    setMileageError('')
    setShowMileageModal(true)
  }
  
  const handleUpdateMileage = async () => {
    const mileageValue = parseInt(newMileage, 10)
    
    if (isNaN(mileageValue) || mileageValue < 0) {
      setMileageError(t('vehicles.invalidMileage') || 'Please enter a valid mileage')
      return
    }
    
    setIsSavingMileage(true)
    try {
      await vehicleApi.updateMileage(id, mileageValue)
      setVehicle(prev => ({ ...prev, current_mileage: mileageValue }))
      setShowMileageModal(false)
    } catch (error) {
      const messageKey = error.response?.data?.message_key
      const apiError = error.response?.data?.error
      setMileageError((messageKey ? t(messageKey) : null) || apiError || t('common.errorOccurred') || 'An error occurred')
    } finally {
      setIsSavingMileage(false)
    }
  }
  
  // Check if vehicle is archived (read-only mode)
  const isArchived = vehicle?.archived === true
  
  const handleFindManual = async () => {
    setManualLoading(true)
    setManualResult(null)
    setShowManualModal(true)
    try {
      const res = await vehicleApi.getManual(id)
      setManualResult(res.data)
    } catch (error) {
      setManualResult({
        manual_url: null,
        source: null,
        fallback_search: `https://www.google.com/search?q=${encodeURIComponent((vehicle?.make || '') + ' ' + (vehicle?.model || '') + ' ' + (vehicle?.year || '') + ' owner manual PDF')}`,
        error: true,
      })
    } finally {
      setManualLoading(false)
    }
  }

  const formatCurrency = (amount) => {
    if (!amount && amount !== 0) return `${currency.symbol}0`
    return `${currency.symbol}${Number(amount).toFixed(2)}`
  }
  
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="skeleton h-14 rounded-xl mb-4" />
        <div className="skeleton h-48 rounded-xl mb-4" />
        <div className="grid grid-cols-2 gap-3 mb-4">
          {[...Array(10)].map((_, i) => (
            <div key={i} className="skeleton h-20 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }
  
  if (!vehicle) return null

  const fuelEconomyUnit = vehicle?.distance_unit || user?.distance_unit || 'km'
  
  // Stats cards configuration
  const statsCards = [
    { 
      id: 'ytdSpent',
      label: t('vehicleDetail.ytdSpent') || 'YTD Spent',
      value: formatCurrency(stats?.ytd_spent || stats?.total_costs || 0),
      icon: Icons.wallet,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      to: `/vehicles/${id}/expenses`
    },
    { 
      id: 'spentThisMonth',
      label: t('vehicleDetail.spentThisMonth') || 'Spent This Month',
      value: formatCurrency(stats?.costs_this_month || 0),
      icon: Icons.calendar,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
      to: `/vehicles/${id}/expenses`
    },
    { 
      id: 'parkingExpense',
      label: t('vehicleDetail.parkingExpense') || 'YTD Parking',
      value: formatCurrency(stats?.parking_ytd_cost ?? stats?.parking_costs ?? 0),
      icon: Icons.parking,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      to: `/vehicles/${id}/expenses?tab=parking`
    },
    { 
      id: 'totalFuelCost',
      label: t('vehicleDetail.totalFuelCost') || 'YTD Fuel Cost',
      value: formatCurrency(stats?.ytd_fuel_costs || 0),
      icon: Icons.fuel,
      color: 'text-amber-500',
      bgColor: 'bg-amber-500/10',
      to: `/vehicles/${id}/expenses?tab=fuel`
    },
    { 
      id: 'totalMileage',
      label: t('vehicleDetail.totalMileage') || 'Total Mileage',
      value: `${(vehicle.current_mileage || 0).toLocaleString()} ${vehicle.distance_unit || 'km'}`,
      icon: Icons.speedometer,
      color: 'text-cyan-500',
      bgColor: 'bg-cyan-500/10'
    },
    { 
      id: 'serviceRecords',
      label: t('vehicleDetail.serviceRecords') || 'Service Records',
      value: stats?.service_count || 0,
      icon: Icons.wrench,
      color: 'text-indigo-500',
      bgColor: 'bg-indigo-500/10',
      to: `/vehicles/${id}/expenses?tab=service`
    },
    { 
      id: 'taxExpenses',
      label: t('vehicleDetail.taxExpenses') || 'YTD Tax',
      value: formatCurrency(stats?.tax_costs || 0),
      icon: Icons.receipt,
      color: 'text-rose-500',
      bgColor: 'bg-rose-500/10',
      to: `/vehicles/${id}/expenses?tab=tax`
    },
    { 
      id: 'insuranceExpenses',
      label: t('vehicleDetail.insuranceExpenses') || 'YTD Insurance',
      value: formatCurrency(stats?.insurance_costs || 0),
      icon: Icons.shield,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
      to: `/vehicles/${id}/expenses?tab=insurance`
    },
    { 
      id: 'fuelEconomy',
      label: t('vehicleDetail.fuelEconomy') || 'Fuel Economy',
      value: formatFuelEconomy(stats?.avg_consumption, fuelEconomyUnit),
      icon: Icons.gauge,
      color: 'text-teal-500',
      bgColor: 'bg-teal-500/10',
      to: `/vehicles/${id}/health`
    },
    { 
      id: 'nextServiceDue',
      label: t('vehicleDetail.nextServiceDue') || 'Next Service Due',
      value: stats?.next_service 
        ? (stats.next_service_days !== null && stats.next_service_days !== undefined
            ? `${stats.next_service_days} ${t('common.days') || 'days'}`
            : formatDate(stats.next_service))
        : '-',
      subValue: stats?.next_service_title || null,
      icon: Icons.clock,
      color: stats?.next_service_days !== null && stats.next_service_days <= 7 ? 'text-red-500' : 'text-orange-500',
      bgColor: stats?.next_service_days !== null && stats.next_service_days <= 7 ? 'bg-red-500/10' : 'bg-orange-500/10',
      to: `/vehicles/${id}/expenses?tab=reminder`
    },
    { 
      id: 'repairRecords',
      label: t('vehicleDetail.repairRecords') || 'Repair Records',
      value: stats?.repair_count || 0,
      icon: Icons.tools,
      color: 'text-red-500',
      bgColor: 'bg-red-500/10',
      to: `/vehicles/${id}/expenses?tab=repair`
    },
  ]
  
  // Action buttons configuration
  const actionButtons = [
    { id: 'search', label: t('vehicleDetail.search') || 'Search', icon: Icons.search, to: `/vehicles/${id}/search` },
    { id: 'expenses', label: t('vehicleDetail.viewExpenses') || 'View Expenses', icon: Icons.expenses, to: `/vehicles/${id}/expenses` },
    { id: 'timeline', label: t('vehicleDetail.timeline') || 'Timeline', icon: Icons.timeline, to: `/vehicles/${id}/timeline` },
    { id: 'charts', label: t('vehicleDetail.charts') || 'Charts', icon: Icons.chart, to: `/vehicles/${id}/charts` },
    { id: 'alerts', label: t('vehicleDetail.predictionAlerts') || 'Prediction Alerts', icon: Icons.alert, to: `/vehicles/${id}/alerts` },
    { id: 'health', label: t('vehicleDetail.vehicleHealth') || 'Vehicle Health', icon: Icons.heart, to: `/vehicles/${id}/health` },
  ]
  
  const addButtons = [
    { id: 'addFuel', label: t('vehicleDetail.addFuel') || 'Add Fuel', icon: Icons.fuel, to: `/vehicles/${id}/fuel/add`, color: 'bg-amber-500' },
    { id: 'addService', label: t('vehicleDetail.addService') || 'Add Service', icon: Icons.wrench, to: `/vehicles/${id}/service/add`, color: 'bg-blue-500' },
    { id: 'addInsurance', label: t('vehicleDetail.addInsurance') || 'Add Insurance', icon: Icons.shield, to: `/vehicles/${id}/insurance/add`, color: 'bg-emerald-500' },
    { id: 'addTax', label: t('vehicleDetail.addTax') || 'Add Tax', icon: Icons.receipt, to: `/vehicles/${id}/tax/add`, color: 'bg-rose-500' },
    { id: 'addParking', label: t('vehicleDetail.addParking') || 'Add Parking', icon: Icons.parking, to: `/vehicles/${id}/parking/add`, color: 'bg-purple-500' },
    { id: 'addRepair', label: t('vehicleDetail.addRepair') || 'Add Repair', icon: Icons.tools, to: `/vehicles/${id}/repair/add`, color: 'bg-red-500' },
    { id: 'addReminder', label: t('vehicleDetail.addReminder') || 'Add Reminder', icon: Icons.bell, to: `/vehicles/${id}/reminder/add`, color: 'bg-green-500' },
    { id: 'addTodo', label: t('vehicleDetail.addTodo') || 'Add Todo', icon: Icons.checkSquare, to: `/vehicles/${id}/todo/add`, color: 'bg-indigo-500' },
  ]
  
  // Get entry type icon and color
  const getEntryTypeStyle = (type) => {
    switch (type) {
      case 'fuel':
        return { icon: Icons.fuel, color: 'text-amber-500', bgColor: 'bg-amber-500/10', label: t('vehicleDetail.typeFuel') || 'Fuel' }
      case 'service':
        return { icon: Icons.wrench, color: 'text-blue-500', bgColor: 'bg-blue-500/10', label: t('vehicleDetail.typeService') || 'Service' }
      case 'repair':
        return { icon: Icons.tools, color: 'text-red-500', bgColor: 'bg-red-500/10', label: t('vehicleDetail.typeRepair') || 'Repair' }
      case 'tax':
        return { icon: Icons.receipt, color: 'text-rose-500', bgColor: 'bg-rose-500/10', label: t('vehicleDetail.typeTax') || 'Tax' }
      case 'parking':
        return { icon: Icons.parking, color: 'text-purple-500', bgColor: 'bg-purple-500/10', label: t('vehicleDetail.typeParking') || 'Parking' }
      case 'insurance':
        return { icon: Icons.shield, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10', label: t('vehicleDetail.typeInsurance') || 'Insurance' }
      default:
        return { icon: Icons.wallet, color: 'text-gray-500', bgColor: 'bg-gray-500/10', label: type }
    }
  }
  
  return (
    <div className="pb-20">
      {/* Archived Banner */}
      {isArchived && (
        <div className="bg-amber-500/20 border-b border-amber-500/30 px-4 py-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
              {Icons.archive}
              <span className="text-sm font-medium">{t('archive.viewingArchived') || 'Viewing archived vehicle (read-only)'}</span>
            </div>
            <button
              onClick={handleArchive}
              className="text-xs font-medium text-amber-600 dark:text-amber-400 hover:underline"
            >
              {t('archive.restore') || 'Restore'}
            </button>
          </div>
        </div>
      )}
      
      {/* Header */}
      <div className="bg-[var(--color-bg-card)] border-b border-[var(--color-border)] px-4 py-3 sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(isArchived ? '/settings' : '/')} className="btn-icon">
            {Icons.arrowBack}
          </button>
          
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold truncate">{vehicle.name}</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">
              {vehicle.make} {vehicle.model} {vehicle.year} • {vehicle.license_plate}
            </p>
          </div>
          
          {/* Only show menu for non-archived vehicles */}
          {!isArchived && (
            <div className="relative">
              <button onClick={() => setShowMenu(!showMenu)} className="btn-icon">
                {Icons.moreVert}
              </button>
              
              {showMenu && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
                  <div className="absolute right-0 top-full mt-1 w-48 bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-xl shadow-xl z-50 overflow-hidden">
                    <Link 
                      to={`/vehicles/${id}/edit`}
                      className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-[var(--color-bg-tertiary)]"
                      onClick={() => setShowMenu(false)}
                    >
                      <span className="text-[var(--color-text-secondary)]">{Icons.edit}</span>
                      {t('vehicleDetail.editVehicle') || 'Edit Vehicle'}
                    </Link>
                    <button 
                      onClick={() => { handleArchive(); setShowMenu(false); }}
                      className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-[var(--color-bg-tertiary)] w-full text-left"
                    >
                      <span className="text-[var(--color-text-secondary)]">{Icons.archive}</span>
                      {t('vehicleDetail.archive') || 'Archive'}
                    </button>
                    <button 
                      onClick={() => { handleDelete(); setShowMenu(false); }}
                      className="flex items-center gap-3 px-4 py-3 text-sm text-red-500 hover:bg-[var(--color-bg-tertiary)] w-full text-left"
                    >
                      {Icons.delete}
                      {t('vehicleDetail.delete') || 'Delete'}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
      
      {/* Main Content */}
      <div className="p-4 space-y-4">
        {/* Desktop: side-by-side | Mobile: stacked */}
        <div className="flex flex-col lg:flex-row lg:gap-4 gap-4">
          {/* Vehicle Photo Section */}
          <div className="card overflow-hidden lg:w-[380px] xl:w-[440px] lg:flex-shrink-0 lg:self-start lg:sticky lg:top-[60px]">
            <div className="relative h-48 lg:h-auto lg:aspect-[4/5] bg-gradient-to-br from-[var(--color-bg-tertiary)] to-[var(--color-bg-secondary)]">
              {vehicle.photo_url ? (
                <img 
                  src={vehicle.photo_url} 
                  alt={vehicle.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-[var(--color-text-muted)]">
                  {Icons.car}
                </div>
              )}
              {/* Mileage Badge - Clickable */}
              <button
                onClick={handleOpenMileageModal}
                disabled={isArchived}
                className="absolute bottom-3 right-3 bg-black/70 backdrop-blur-sm text-white px-3 py-1.5 rounded-lg hover:bg-black/80 transition-colors group disabled:cursor-not-allowed"
                title={t('vehicles.updateMileage') || 'Update mileage'}
              >
                <div className="flex items-center gap-2">
                  <div className="flex items-baseline gap-1">
                    <span className="text-lg font-bold">{(vehicle.current_mileage || 0).toLocaleString()}</span>
                    <span className="text-xs opacity-80">{vehicle.distance_unit || 'km'}</span>
                  </div>
                  {!isArchived && (
                    <span className="opacity-60 group-hover:opacity-100 transition-opacity">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </span>
                  )}
                </div>
              </button>
            </div>
          </div>
          
          {/* Stats Cards Grid */}
          <div className="flex-1 min-w-0">
            <div className="grid grid-cols-2 gap-3">
              {statsCards.map(stat => {
                const cardContent = (
                  <>
                    <div className={`w-10 h-10 rounded-lg ${stat.bgColor} flex items-center justify-center ${stat.color} flex-shrink-0`}>
                      {stat.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-[var(--color-text-muted)] truncate">{stat.label}</p>
                      <p className="text-sm font-bold truncate">{stat.value}</p>
                      {stat.subValue && (
                        <p className="text-xs text-[var(--color-text-secondary)] truncate">{stat.subValue}</p>
                      )}
                    </div>
                    {stat.to && (
                      <svg className={`w-3.5 h-3.5 flex-shrink-0 ${stat.color} opacity-40`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 18l6-6-6-6"/>
                      </svg>
                    )}
                  </>
                )
                return stat.to ? (
                  <Link
                    key={stat.id}
                    to={stat.to}
                    className="card flex items-center gap-3 p-3 hover:bg-[var(--color-bg-tertiary)] active:scale-[0.98] transition-all cursor-pointer"
                  >
                    {cardContent}
                  </Link>
                ) : (
                  <div key={stat.id} className="card flex items-center gap-3 p-3">
                    {cardContent}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
        
        {/* Recent Activity Section */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold">{t('vehicleDetail.recentActivity') || 'Recent Activity'}</h3>
          </div>
          
          {/* Action Buttons */}
          <div className="flex flex-wrap gap-2 mb-4">
            {actionButtons.map(btn => (
              <Link
                key={btn.id}
                to={btn.to}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-bg-secondary)] rounded-lg transition-colors"
              >
                <span className="text-[var(--color-text-secondary)]">{btn.icon}</span>
                {btn.label}
              </Link>
            ))}
            <button
              onClick={handleFindManual}
              disabled={manualLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--color-bg-tertiary)] hover:bg-[var(--color-bg-secondary)] rounded-lg transition-colors"
            >
              <span className="text-[var(--color-text-secondary)]">{Icons.bookOpen}</span>
              {manualLoading
                ? (t('vehicleManual.loading') || 'Looking for manual...')
                : (t('vehicleDetail.vehicleManual') || 'Owner\'s Manual')}
            </button>
          </div>
          
          {/* Add Buttons - Hide for archived vehicles */}
          {!isArchived && (
            <div className="flex flex-wrap gap-2 mb-4">
              {addButtons.map(btn => (
                <Link
                  key={btn.id}
                  to={btn.to}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white ${btn.color} hover:opacity-90 rounded-lg transition-opacity`}
                >
                  <span>{Icons.plus}</span>
                  {btn.label}
                </Link>
              ))}
            </div>
          )}
          
          {/* Activity Table */}
          {timeline.length > 0 ? (
            <div className="overflow-x-auto -mx-4 px-4">
              <table className="w-full min-w-[400px]">
                <thead>
                  <tr className="border-b border-[var(--color-border)]">
                    <th className="text-left text-xs font-medium text-[var(--color-text-muted)] pb-2 pr-4">
                      {t('vehicleDetail.date') || 'Date'}
                    </th>
                    <th className="text-left text-xs font-medium text-[var(--color-text-muted)] pb-2 pr-4">
                      {t('vehicleDetail.type') || 'Type'}
                    </th>
                    <th className="text-left text-xs font-medium text-[var(--color-text-muted)] pb-2 pr-4">
                      {t('vehicleDetail.description') || 'Description'}
                    </th>
                    <th className="text-right text-xs font-medium text-[var(--color-text-muted)] pb-2">
                      {t('vehicleDetail.cost') || 'Cost'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {timeline.slice(0, 10).map((entry, i) => {
                    const typeStyle = getEntryTypeStyle(entry.type)
                    return (
                      <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
                        <td className="py-3 pr-4 text-xs text-[var(--color-text-secondary)]">
                          {formatDate(entry.date)}
                        </td>
                        <td className="py-3 pr-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-medium ${typeStyle.bgColor} ${typeStyle.color}`}>
                            {typeStyle.label}
                          </span>
                        </td>
                        <td className="py-3 pr-4 text-sm truncate max-w-[150px]">
                          {entry.description}
                        </td>
                        <td className="py-3 text-right text-sm font-medium">
                          {formatCurrency(entry.cost)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-sm text-[var(--color-text-secondary)]">
                {t('vehicleDetail.noActivity') || 'No recent activity'}
              </p>
            </div>
          )}
        </div>
      </div>
      
      {/* Mileage Update Modal */}
      {showManualModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowManualModal(false)}
          />
          <div className="relative bg-[var(--color-bg-secondary)] rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
            <h3 className="text-lg font-semibold mb-1 flex items-center gap-2">
              <span className="text-[var(--color-accent)]">{Icons.bookOpen}</span>
              {t('vehicleManual.title') || "Owner's Manual"}
            </h3>
            {vehicle && (
              <p className="text-xs text-[var(--color-text-muted)] mb-4">
                {vehicle.make} {vehicle.model} {vehicle.year}
              </p>
            )}

            {manualLoading && (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent" />
                <span className="ml-3 text-sm text-[var(--color-text-secondary)]">
                  {t('vehicleManual.loading') || 'Looking for manual...'}
                </span>
              </div>
            )}

            {!manualLoading && manualResult && manualResult.manual_url && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${
                    manualResult.source === 'oem' 
                      ? 'bg-green-500/10 text-green-500' 
                      : 'bg-blue-500/10 text-blue-500'
                  }`}>
                    {manualResult.source === 'oem' 
                      ? (t('vehicleManual.sourceOem') || 'Official source')
                      : (t('vehicleManual.sourceAggregator') || 'Third-party source')}
                  </span>
                </div>
                <a
                  href={manualResult.manual_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary w-full flex items-center justify-center gap-2"
                >
                  {t('vehicleManual.viewManual') || 'View Manual'}
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
                </a>
                <p className="text-[10px] text-[var(--color-text-muted)] text-center">
                  {t('vehicleManual.openInNewTab') || 'Opens in a new tab'}
                </p>
              </div>
            )}

            {!manualLoading && manualResult && !manualResult.manual_url && (
              <div className="space-y-3">
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {t('vehicleManual.notFound') || 'Manual not found for this vehicle.'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('vehicleManual.notFoundHint') || "Try the manufacturer's website"}
                </p>
                {manualResult.fallback_search && (
                  <a
                    href={manualResult.fallback_search}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-secondary w-full flex items-center justify-center gap-2"
                  >
                    {t('vehicleManual.searchOnline') || 'Search online'}
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                  </a>
                )}
              </div>
            )}

            <button
              onClick={() => setShowManualModal(false)}
              className="btn btn-secondary w-full mt-4"
            >
              {t('common.close') || 'Close'}
            </button>
          </div>
        </div>
      )}

      {showMileageModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowMileageModal(false)}
          />
          
          {/* Modal */}
          <div className="relative bg-[var(--color-bg-secondary)] rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
            <h3 className="text-lg font-semibold mb-4">
              {t('vehicles.updateMileage') || 'Update Mileage'}
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  {t('vehicles.currentMileage') || 'Current Mileage'} ({vehicle?.distance_unit || 'km'})
                </label>
                <input
                  type="number"
                  value={newMileage}
                  onChange={(e) => {
                    setNewMileage(e.target.value)
                    setMileageError('')
                  }}
                  className="input w-full text-lg font-mono"
                  min={0}
                  placeholder="0"
                  autoFocus
                />
                {mileageError && (
                  <p className="text-red-500 text-xs mt-1">{mileageError}</p>
                )}
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  {t('vehicles.previousMileage') || 'Previous'}: {(vehicle?.current_mileage || 0).toLocaleString()} {vehicle?.distance_unit || 'km'}
                </p>
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={() => setShowMileageModal(false)}
                  className="btn btn-secondary flex-1"
                  disabled={isSavingMileage}
                >
                  {t('common.cancel') || 'Cancel'}
                </button>
                <button
                  onClick={handleUpdateMileage}
                  className="btn btn-primary flex-1"
                  disabled={isSavingMileage}
                >
                  {isSavingMileage ? (t('common.saving') || 'Saving...') : (t('common.save') || 'Save')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
