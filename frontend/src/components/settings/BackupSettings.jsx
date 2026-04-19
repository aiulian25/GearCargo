import { useState, useEffect, useRef } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { backupApi } from '../../services/api'
import toast from 'react-hot-toast'

// SVG Icons
const Icons = {
  cloud: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
    </svg>
  ),
  download: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  ),
  upload: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
    </svg>
  ),
  clock: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  server: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
    </svg>
  ),
  trash: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  ),
  refresh: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
    </svg>
  ),
  check: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  ),
  x: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  folder: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
    </svg>
  ),
  chevronDown: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  ),
  chevronUp: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
    </svg>
  ),
}

export default function BackupSettings() {
  const { t } = useTranslation()
  const fileInputRef = useRef(null)
  const lubelogFileInputRef = useRef(null)
  const uploadInputRef = useRef(null)
  
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [backing, setBacking] = useState(false)
  const [sendingExternal, setSendingExternal] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importingLubelog, setImportingLubelog] = useState(false)
  const [lubelogDistanceUnit, setLubelogDistanceUnit] = useState('miles')
  const [testingConnection, setTestingConnection] = useState(false)
  const [visibleApiKeyDestinations, setVisibleApiKeyDestinations] = useState({})
  const [uploading, setUploading] = useState(false)
  const [externalFiles, setExternalFiles] = useState(null)
  const [browsingFiles, setBrowsingFiles] = useState(false)
  const [restoringExternal, setRestoringExternal] = useState(false)
  
  const [status, setStatus] = useState(null)
  const createEmptyDestination = (index = 1) => ({
    id: `destination_${Date.now()}_${index}`,
    name: `${t('backup.destinationLabel') || 'Destination'} ${index}`,
    provider: 'webdav',
    enabled: true,
    external_url: '',
    external_api_key: '',
    has_external_api_key: false,
    external_path: '/GearCargo',
  })

  const normalizeDestinations = (incomingDestinations, fallbackSchedule = {}) => {
    if (Array.isArray(incomingDestinations) && incomingDestinations.length > 0) {
      return incomingDestinations.map((destination, index) => ({
        id: destination.id || `destination_${index + 1}`,
        name: destination.name || `${t('backup.destinationLabel') || 'Destination'} ${index + 1}`,
        provider: destination.provider || 'webdav',
        enabled: destination.enabled !== false,
        external_url: destination.external_url || '',
        external_api_key: destination.external_api_key || '',
        has_external_api_key: Boolean(destination.has_external_api_key),
        external_path: destination.external_path || '/GearCargo',
      }))
    }

    if (fallbackSchedule.external_url) {
      return [{
        id: 'legacy_primary',
        name: t('backup.primaryDestination') || 'Primary Destination',
        provider: 'webdav',
        enabled: Boolean(fallbackSchedule.external_enabled),
        external_url: fallbackSchedule.external_url || '',
        external_api_key: '',
        has_external_api_key: Boolean(fallbackSchedule.has_external_api_key),
        external_path: fallbackSchedule.external_path || '/GearCargo',
      }]
    }

    return [createEmptyDestination(1)]
  }

  const syncLegacyExternalFields = (nextSchedule) => {
    const destinations = Array.isArray(nextSchedule.external_destinations)
      ? nextSchedule.external_destinations
      : []

    const firstEnabledDestination = destinations.find((destination) => destination.enabled)
    const primaryDestination = firstEnabledDestination || destinations[0]

    return {
      ...nextSchedule,
      external_enabled: destinations.some((destination) => destination.enabled),
      external_url: primaryDestination?.external_url || '',
      external_path: primaryDestination?.external_path || '/GearCargo',
      has_external_api_key: Boolean(primaryDestination?.has_external_api_key || primaryDestination?.external_api_key),
      external_destinations: destinations,
    }
  }

  const [schedule, setSchedule] = useState({
    enabled: false,
    frequency: 'weekly',
    day_of_week: 0,
    day_of_month: 1,
    hour: 3,
    include_attachments: true,
    external_enabled: false,
    external_url: '',
    external_api_key: '',
    external_path: '/GearCargo',
    external_destinations: [
      {
        id: 'destination_1',
        name: 'Destination 1',
        provider: 'webdav',
        enabled: false,
        external_url: '',
        external_api_key: '',
        has_external_api_key: false,
        external_path: '/GearCargo',
      }
    ],
    retention_days: 90,
    max_backups: 10,
    notify_on_success: false,
    notify_on_failure: true,
  })
  
  const [showExternalSettings, setShowExternalSettings] = useState(false)
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false)
  const [showBackupList, setShowBackupList] = useState(false)
  const [selectedExternalDestinationIndex, setSelectedExternalDestinationIndex] = useState(0)
  const [browsingFolders, setBrowsingFolders] = useState(false)
  const [externalFolders, setExternalFolders] = useState(null)
  const [browsePath, setBrowsePath] = useState('/')
  
  const dayNames = [
    t('backup.monday') || 'Monday',
    t('backup.tuesday') || 'Tuesday',
    t('backup.wednesday') || 'Wednesday',
    t('backup.thursday') || 'Thursday',
    t('backup.friday') || 'Friday',
    t('backup.saturday') || 'Saturday',
    t('backup.sunday') || 'Sunday',
  ]
  
  useEffect(() => {
    loadBackupStatus()
  }, [])
  
  const loadBackupStatus = async () => {
    try {
      setLoading(true)
      const response = await backupApi.getStatus()
      setStatus(response.data)
      
      if (response.data.schedule) {
        const loadedSchedule = response.data.schedule
        const normalizedDestinations = normalizeDestinations(
          loadedSchedule.external_destinations,
          loadedSchedule
        )
        setSchedule((prev) => syncLegacyExternalFields({
          ...prev,
          ...loadedSchedule,
          external_destinations: normalizedDestinations,
        }))
        setShowExternalSettings(
          Boolean(loadedSchedule.external_enabled) || normalizedDestinations.some((destination) => destination.enabled)
        )
        setSelectedExternalDestinationIndex(0)
      }
    } catch (error) {
      console.error('Failed to load backup status:', error)
      toast.error(t('backup.loadFailed') || 'Failed to load backup settings')
    } finally {
      setLoading(false)
    }
  }
  
  const handleScheduleChange = (field, value) => {
    setSchedule(prev => ({ ...prev, [field]: value }))
  }

  const updateDestinationList = (updater) => {
    setSchedule((prev) => {
      const current = Array.isArray(prev.external_destinations) ? prev.external_destinations : []
      const updated = updater(current)
      return syncLegacyExternalFields({ ...prev, external_destinations: updated })
    })
  }

  const updateExternalDestination = (index, field, value) => {
    updateDestinationList((destinations) => destinations.map((destination, destinationIndex) => {
      if (destinationIndex !== index) return destination
      const updatedDestination = { ...destination, [field]: value }
      if (field === 'external_api_key') {
        updatedDestination.has_external_api_key = Boolean(value)
      }
      return updatedDestination
    }))
  }

  const addExternalDestination = () => {
    updateDestinationList((destinations) => {
      const next = [...destinations, createEmptyDestination(destinations.length + 1)]
      return next
    })
    setSelectedExternalDestinationIndex((prev) => prev + 1)
  }

  const removeExternalDestination = (index) => {
    updateDestinationList((destinations) => {
      if (destinations.length <= 1) {
        return [createEmptyDestination(1)]
      }
      return destinations.filter((_, destinationIndex) => destinationIndex !== index)
    })
    setSelectedExternalDestinationIndex((prev) => Math.max(0, prev - (index <= prev ? 1 : 0)))
  }

  const toggleDestinationApiKeyVisibility = (destinationId) => {
    setVisibleApiKeyDestinations((prev) => ({
      ...prev,
      [destinationId]: !prev[destinationId],
    }))
  }

  const isDestinationApiKeyVisible = (destinationId) => Boolean(visibleApiKeyDestinations[destinationId])

  const moveExternalDestination = (index, direction) => {
    updateDestinationList((destinations) => {
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= destinations.length) {
        return destinations
      }

      const next = [...destinations]
      const [moved] = next.splice(index, 1)
      next.splice(targetIndex, 0, moved)
      return next
    })

    setSelectedExternalDestinationIndex((prev) => {
      if (prev === index) return index + direction
      if (prev === index + direction) return index
      return prev
    })
  }

  const getActiveDestination = () => {
    const destinations = Array.isArray(schedule.external_destinations) ? schedule.external_destinations : []
    if (!destinations.length) return null
    const safeIndex = Math.min(selectedExternalDestinationIndex, destinations.length - 1)
    return destinations[safeIndex]
  }
  
  const saveSchedule = async () => {
    try {
      setSaving(true)

      const destinations = (schedule.external_destinations || []).map((destination, index) => ({
        id: destination.id || `destination_${index + 1}`,
        name: destination.name || `${t('backup.destinationLabel') || 'Destination'} ${index + 1}`,
        provider: destination.provider || 'webdav',
        enabled: destination.enabled !== false,
        external_url: (destination.external_url || '').trim(),
        external_api_key: (destination.external_api_key || '').trim(),
        external_path: destination.external_path || '/GearCargo',
        has_external_api_key: Boolean(destination.has_external_api_key),
      }))
      
      if (schedule.external_enabled) {
        const enabledDestinations = destinations.filter((destination) => destination.enabled)
        if (!enabledDestinations.length) {
          toast.error(t('backup.enableAtLeastOneDestination') || 'Enable at least one destination')
          return
        }

        for (const destination of enabledDestinations) {
          if (!destination.external_url) {
            toast.error(t('backup.enterDestinationUrl') || 'Please enter a destination URL')
            return
          }
          if (!destination.external_url.startsWith('https://')) {
            toast.error(t('backup.httpsRequired') || 'External URL must use HTTPS')
            return
          }
          if (!destination.external_api_key && !destination.has_external_api_key) {
            toast.error(t('backup.enterDestinationKey') || 'Please enter credentials for each destination')
            return
          }
        }
      }

      const enabledDestinations = destinations.filter((destination) => destination.enabled)
      const primaryDestination = enabledDestinations[0] || destinations[0]

      const schedulePayload = {
        ...schedule,
        external_enabled: schedule.external_enabled,
        external_url: primaryDestination?.external_url || '',
        external_api_key: primaryDestination?.external_api_key || '',
        external_path: primaryDestination?.external_path || '/GearCargo',
        external_destinations: destinations.map((destination) => ({
          id: destination.id,
          name: destination.name,
          provider: destination.provider,
          enabled: destination.enabled,
          external_url: destination.external_url,
          external_api_key: destination.external_api_key,
          external_path: destination.external_path,
          has_external_api_key: destination.has_external_api_key,
        })),
      }
      
      await backupApi.updateSchedule(schedulePayload)
      toast.success(t('backup.scheduleSaved') || 'Backup schedule saved')
      loadBackupStatus()
    } catch (error) {
      console.error('Failed to save schedule:', error)
      toast.error(error.response?.data?.error || t('backup.saveFailed') || 'Failed to save schedule')
    } finally {
      setSaving(false)
    }
  }
  
  const runBackupNow = async () => {
    try {
      setBacking(true)
      const response = await backupApi.runNow(schedule.include_attachments, schedule.external_enabled)
      if (response.data.external_error) {
        toast.error(`${t('backup.externalFailed') || 'External upload failed'}: ${response.data.external_error}`)
        toast.success(t('backup.backupSavedLocally') || 'Backup saved locally')
      } else {
        toast.success(t('backup.backupComplete') || 'Backup completed successfully')
      }
      loadBackupStatus()
    } catch (error) {
      console.error('Backup failed:', error)
      toast.error(error.response?.data?.error || t('backup.backupFailed') || 'Backup failed')
    } finally {
      setBacking(false)
    }
  }
  
  const downloadBackup = async () => {
    try {
      setBacking(true)
      const response = await backupApi.export('zip', schedule.include_attachments, false)
      
      // Create download link
      const blob = new Blob([response.data], { type: 'application/zip' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `gearcargo_backup_${new Date().toISOString().split('T')[0]}.zip`
      a.click()
      URL.revokeObjectURL(url)
      
      toast.success(t('backup.downloadComplete') || 'Backup downloaded')
    } catch (error) {
      console.error('Download failed:', error)
      toast.error(t('backup.downloadFailed') || 'Failed to download backup')
    } finally {
      setBacking(false)
    }
  }
  
  const handleImportClick = () => {
    fileInputRef.current?.click()
  }
  
  const handleImportFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    
    // Validate file type
    const validTypes = ['.json', '.zip']
    const hasValidExtension = validTypes.some(ext => file.name.toLowerCase().endsWith(ext))
    if (!hasValidExtension) {
      toast.error(t('backup.invalidFileType') || 'Please select a JSON or ZIP file')
      event.target.value = ''
      return
    }
    
    // Confirm before importing
    if (!window.confirm(t('backup.importConfirm') || 'This will merge the backup data with your existing data. Continue?')) {
      event.target.value = ''
      return
    }
    
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('merge_mode', 'merge')
      
      const response = await backupApi.import(formData)
      
      const imported = response.data.imported || {}
      const summary = []
      if (imported.vehicles > 0) summary.push(`${imported.vehicles} ${t('backup.vehicles') || 'vehicles'}`)
      if (imported.fuel_entries > 0) summary.push(`${imported.fuel_entries} ${t('backup.fuelEntries') || 'fuel entries'}`)
      if (imported.service_entries > 0) summary.push(`${imported.service_entries} ${t('backup.serviceEntries') || 'service entries'}`)
      if (imported.attachments > 0) summary.push(`${imported.attachments} ${t('backup.attachments') || 'attachments'}`)
      
      toast.success(
        summary.length > 0 
          ? `${t('backup.importSuccess') || 'Import completed'}: ${summary.join(', ')}`
          : t('backup.importSuccess') || 'Import completed'
      )
      
      // Reload page to refresh all data
      setTimeout(() => window.location.reload(), 1500)
    } catch (error) {
      console.error('Import failed:', error)
      toast.error(error.response?.data?.error || t('backup.importFailed') || 'Failed to import data')
    } finally {
      setImporting(false)
      event.target.value = ''
    }
  }
  
  const handleLubelogImportClick = () => {
    lubelogFileInputRef.current?.click()
  }

  const handleLubelogImportFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.zip')) {
      toast.error(t('backup.lubelogInvalidFile') || 'Please select a LubeLogger backup ZIP file')
      event.target.value = ''
      return
    }

    if (!window.confirm(t('backup.lubelogImportConfirm') || 'Import data from LubeLogger backup? This will create new vehicles and entries.')) {
      event.target.value = ''
      return
    }

    setImportingLubelog(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('merge_mode', 'merge')
      formData.append('distance_unit', lubelogDistanceUnit)

      const response = await backupApi.importLubelog(formData)

      const imported = response.data.imported || {}
      const summary = []
      if (imported.vehicles > 0) summary.push(`${imported.vehicles} ${t('backup.vehicles') || 'vehicles'}`)
      if (imported.fuel_entries > 0) summary.push(`${imported.fuel_entries} ${t('backup.fuelEntries') || 'fuel entries'}`)
      if (imported.service_entries > 0) summary.push(`${imported.service_entries} ${t('backup.serviceEntries') || 'service entries'}`)
      if (imported.repair_entries > 0) summary.push(`${imported.repair_entries} ${t('backup.repairEntries') || 'repair entries'}`)
      if (imported.tax_entries > 0) summary.push(`${imported.tax_entries} ${t('backup.taxEntries') || 'tax entries'}`)
      if (imported.insurance_policies > 0) summary.push(`${imported.insurance_policies} ${t('backup.insurancePolicies') || 'insurance policies'}`)
      if (imported.reminders > 0) summary.push(`${imported.reminders} ${t('backup.reminders') || 'reminders'}`)
      if (imported.attachments > 0) summary.push(`${imported.attachments} ${t('backup.attachments') || 'attachments'}`)

      toast.success(
        summary.length > 0
          ? `${t('backup.lubelogImportSuccess') || 'LubeLogger import completed'}: ${summary.join(', ')}`
          : t('backup.lubelogImportSuccess') || 'LubeLogger import completed'
      )

      setTimeout(() => window.location.reload(), 1500)
    } catch (error) {
      console.error('LubeLogger import failed:', error)
      toast.error(error.response?.data?.error || t('backup.lubelogImportFailed') || 'Failed to import LubeLogger data')
    } finally {
      setImportingLubelog(false)
      event.target.value = ''
    }
  }

  const restoreBackup = async (filename) => {
    if (!window.confirm(t('backup.restoreConfirm') || 'Restore this backup? This will merge data with your existing records.')) {
      return
    }
    
    try {
      setImporting(true)
      await backupApi.restoreFromStorage(filename, 'merge')
      toast.success(t('backup.restoreSuccess') || 'Backup restored successfully')
      setTimeout(() => window.location.reload(), 1500)
    } catch (error) {
      console.error('Restore failed:', error)
      toast.error(error.response?.data?.error || t('backup.restoreFailed') || 'Failed to restore backup')
    } finally {
      setImporting(false)
    }
  }
  
  const deleteBackup = async (filename) => {
    if (!window.confirm(t('backup.deleteConfirm') || 'Delete this backup permanently?')) {
      return
    }
    
    try {
      await backupApi.deleteBackup(filename)
      toast.success(t('backup.deleteSuccess') || 'Backup deleted')
      loadBackupStatus()
    } catch (error) {
      console.error('Delete failed:', error)
      toast.error(t('backup.deleteFailed') || 'Failed to delete backup')
    }
  }

  const handleUploadClick = () => {
    uploadInputRef.current?.click()
  }

  const handleUploadFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (!file.name.toLowerCase().endsWith('.zip')) {
      toast.error(t('backup.invalidZipFile') || 'Please select a .zip backup file')
      event.target.value = ''
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await backupApi.uploadBackup(formData)
      toast.success(response.data.message || 'Backup uploaded')
      loadBackupStatus()
    } catch (error) {
      console.error('Upload failed:', error)
      toast.error(error.response?.data?.error || 'Failed to upload backup')
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }

  const browseExternalFiles = async () => {
    const activeDestination = getActiveDestination()
    if (!activeDestination?.external_url || (!activeDestination.external_api_key && !activeDestination.has_external_api_key)) {
      toast.error(t('backup.enterUrlAndKey') || 'Enter server URL and credentials first')
      return
    }
    try {
      setBrowsingFiles(true)
      const response = await backupApi.browseExternalFiles(
        activeDestination.external_url,
        activeDestination.external_api_key || null,
        activeDestination.external_path
      )
      setExternalFiles(response.data.files)
    } catch (error) {
      console.error('Browse files failed:', error)
      toast.error(error.response?.data?.error || 'Failed to browse external files')
    } finally {
      setBrowsingFiles(false)
    }
  }

  const restoreFromExternal = async (filename) => {
    const activeDestination = getActiveDestination()
    if (!window.confirm(t('backup.restoreExternalConfirm') || `Restore from external backup "${filename}"? This will merge data with your existing records.`)) {
      return
    }
    try {
      setRestoringExternal(true)
      const response = await backupApi.restoreFromExternal(
        filename,
        activeDestination?.external_url,
        activeDestination?.external_api_key || null,
        activeDestination?.external_path
      )
      const imported = response.data.imported || {}
      const summary = []
      if (imported.vehicles > 0) summary.push(`${imported.vehicles} vehicles`)
      if (imported.fuel_entries > 0) summary.push(`${imported.fuel_entries} fuel entries`)
      if (imported.service_entries > 0) summary.push(`${imported.service_entries} service entries`)
      if (imported.attachments > 0) summary.push(`${imported.attachments} attachments`)
      toast.success(
        summary.length > 0
          ? `Restored: ${summary.join(', ')}`
          : 'Restore completed'
      )
      setExternalFiles(null)
      loadBackupStatus()
    } catch (error) {
      console.error('External restore failed:', error)
      toast.error(error.response?.data?.error || 'Failed to restore from external')
    } finally {
      setRestoringExternal(false)
    }
  }
  
  const testExternalConnection = async () => {
    const activeDestination = getActiveDestination()
    if (!activeDestination?.external_url) {
      toast.error(t('backup.enterUrl') || 'Please enter an external URL')
      return
    }
    
    if (!activeDestination.external_url.startsWith('https://')) {
      toast.error(t('backup.httpsRequired') || 'External URL must use HTTPS')
      return
    }
    
    try {
      setTestingConnection(true)
      const response = await backupApi.testExternalConnection(
        activeDestination.external_url,
        activeDestination.external_api_key,
        activeDestination.external_path
      )
      
      if (response.data.success) {
        toast.success(response.data.message || t('backup.connectionSuccess') || 'Connection successful')
      } else {
        toast.error(response.data.error || t('backup.connectionFailed') || 'Connection failed')
      }
    } catch (error) {
      console.error('Connection test failed:', error)
      toast.error(t('backup.connectionFailed') || 'Connection test failed')
    } finally {
      setTestingConnection(false)
    }
  }

  const browseExternalFolders = async (path = '/') => {
    const activeDestination = getActiveDestination()
    if (!activeDestination?.external_url || (!activeDestination.external_api_key && !activeDestination.has_external_api_key)) {
      toast.error(t('backup.enterUrlAndKey') || 'Enter server URL and credentials first')
      return
    }
    try {
      setBrowsingFolders(true)
      const response = await backupApi.browseExternalFolders(
        activeDestination.external_url,
        activeDestination.external_api_key || null,
        path
      )
      setExternalFolders(response.data.folders)
      setBrowsePath(path)
    } catch (error) {
      console.error('Browse failed:', error)
      toast.error(error.response?.data?.error || 'Failed to browse folders')
    } finally {
      setBrowsingFolders(false)
    }
  }

  const selectExternalFolder = (folder) => {
    const newPath = browsePath === '/' ? `/${folder}` : `${browsePath}/${folder}`
    updateExternalDestination(selectedExternalDestinationIndex, 'external_path', newPath)
    setExternalFolders(null)
  }

  const activeDestination = getActiveDestination()
  
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[var(--color-accent)]">{Icons.cloud}</span>
        <div>
          <h3 className="text-sm font-medium">{t('backup.title') || 'Auto Backup'}</h3>
          <p className="text-2xs text-[var(--color-text-muted)]">
            {t('backup.description') || 'Schedule automatic backups with attachments'}
          </p>
        </div>
      </div>
      
      {/* Last Backup Info */}
      {status?.last_backup && (
        <div className="bg-green-500/10 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
            {Icons.check}
            <span className="text-sm font-medium">
              {t('backup.lastBackup') || 'Last backup'}: {new Date(status.last_backup).toLocaleString()}
            </span>
          </div>
          {status.last_backup_details && (
            <p className="text-2xs text-[var(--color-text-muted)] mt-1 ml-6">
              {status.last_backup_details.vehicles_count || 0} {t('backup.vehicles') || 'vehicles'}, 
              {' '}{status.last_backup_details.entries_count || 0} {t('backup.entries') || 'entries'}, 
              {' '}{status.last_backup_details.attachments_count || 0} {t('backup.attachments') || 'attachments'}
              {status.last_backup_details.file_size_human && ` • ${status.last_backup_details.file_size_human}`}
            </p>
          )}
        </div>
      )}
      
      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <button
          onClick={downloadBackup}
          disabled={backing}
          className="flex flex-col items-center gap-2 p-4 bg-[var(--color-bg-tertiary)] rounded-xl hover:bg-[var(--color-bg-tertiary)]/80 transition-colors"
        >
          <span className="text-[var(--color-accent)]">
            {backing ? (
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : Icons.download}
          </span>
          <span className="text-xs font-medium">{t('backup.downloadBackup') || 'Download'}</span>
        </button>
        
        <button
          onClick={handleImportClick}
          disabled={importing}
          className="flex flex-col items-center gap-2 p-4 bg-[var(--color-bg-tertiary)] rounded-xl hover:bg-[var(--color-bg-tertiary)]/80 transition-colors"
        >
          <span className="text-[var(--color-accent)]">
            {importing ? (
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : Icons.refresh}
          </span>
          <span className="text-xs font-medium">{t('backup.restoreBackup') || 'Restore'}</span>
        </button>

        <button
          onClick={handleUploadClick}
          disabled={uploading}
          className="flex flex-col items-center gap-2 p-4 bg-[var(--color-bg-tertiary)] rounded-xl hover:bg-[var(--color-bg-tertiary)]/80 transition-colors"
        >
          <span className="text-[var(--color-accent)]">
            {uploading ? (
              <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : Icons.upload}
          </span>
          <span className="text-xs font-medium">{t('backup.uploadBackup') || 'Upload'}</span>
        </button>
        
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,.zip"
          onChange={handleImportFile}
          className="hidden"
        />
        <input
          ref={uploadInputRef}
          type="file"
          accept=".zip"
          onChange={handleUploadFile}
          className="hidden"
        />
      </div>
      
      {/* Import from LubeLogger */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-[var(--color-text-muted)]">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12l-3-3m0 0l-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          </span>
          <div>
            <span className="text-sm font-medium">{t('backup.lubelogImport') || 'Import from LubeLogger'}</span>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('backup.lubelogImportDesc') || 'Import vehicles, fuel logs, services, and more from a LubeLogger backup'}
            </p>
          </div>
        </div>

        {/* Distance Unit Selector */}
        <div className="mb-3">
          <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
            {t('backup.distanceUnit') || 'Distance Unit'}
          </label>
          <div className="grid grid-cols-2 gap-2">
            {['miles', 'km'].map((unit) => (
              <button
                key={unit}
                type="button"
                onClick={() => setLubelogDistanceUnit(unit)}
                className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                  lubelogDistanceUnit === unit
                    ? 'bg-[var(--color-accent)] text-white'
                    : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80'
                }`}
              >
                {unit === 'miles' ? (t('backup.miles') || 'Miles') : (t('backup.km') || 'Kilometres')}
              </button>
            ))}
          </div>
          <p className="text-2xs text-[var(--color-text-muted)] mt-1">
            {t('backup.distanceUnitHint') || 'Odometer readings will be converted if needed'}
          </p>
        </div>

        <button
          onClick={handleLubelogImportClick}
          disabled={importingLubelog}
          className="w-full py-2.5 px-4 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80 transition-colors flex items-center justify-center gap-2"
        >
          {importingLubelog ? (
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            Icons.upload
          )}
          <span>{importingLubelog ? (t('backup.importing') || 'Importing...') : (t('backup.selectLubelogBackup') || 'Select LubeLogger Backup (.zip)')}</span>
        </button>
        <input
          ref={lubelogFileInputRef}
          type="file"
          accept=".zip"
          onChange={handleLubelogImportFile}
          className="hidden"
        />
      </div>

      {/* Auto Backup Toggle */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-text-muted)]">{Icons.clock}</span>
            <div>
              <span className="text-sm font-medium">{t('backup.autoBackup') || 'Automatic Backup'}</span>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('backup.autoBackupDesc') || 'Schedule regular backups'}
              </p>
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={(e) => handleScheduleChange('enabled', e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-10 h-6 bg-[var(--color-bg-secondary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]" />
          </label>
        </div>
        
        {schedule.enabled && (
          <div className="space-y-4 pt-4 border-t border-[var(--color-border)]">
            {/* Frequency */}
            <div>
              <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                {t('backup.frequency') || 'Frequency'}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {['weekly', 'monthly', 'quarterly'].map((freq) => (
                  <button
                    key={freq}
                    onClick={() => handleScheduleChange('frequency', freq)}
                    className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                      schedule.frequency === freq
                        ? 'bg-[var(--color-accent)] text-white'
                        : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80'
                    }`}
                  >
                    {t(`backup.${freq}`) || freq.charAt(0).toUpperCase() + freq.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Day Selection */}
            {schedule.frequency === 'weekly' && (
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                  {t('backup.dayOfWeek') || 'Day of Week'}
                </label>
                <select
                  value={schedule.day_of_week}
                  onChange={(e) => handleScheduleChange('day_of_week', parseInt(e.target.value))}
                  className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                >
                  {dayNames.map((day, index) => (
                    <option key={index} value={index}>{day}</option>
                  ))}
                </select>
              </div>
            )}
            
            {(schedule.frequency === 'monthly' || schedule.frequency === 'quarterly') && (
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                  {t('backup.dayOfMonth') || 'Day of Month'}
                </label>
                <select
                  value={schedule.day_of_month}
                  onChange={(e) => handleScheduleChange('day_of_month', parseInt(e.target.value))}
                  className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                >
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                    <option key={day} value={day}>{day}</option>
                  ))}
                </select>
              </div>
            )}
            
            {/* Include Attachments */}
            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-sm">{t('backup.includeAttachments') || 'Include Attachments'}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {t('backup.includeAttachmentsDesc') || 'Backup uploaded files and receipts'}
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={schedule.include_attachments}
                  onChange={(e) => handleScheduleChange('include_attachments', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-10 h-6 bg-[var(--color-bg-secondary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]" />
              </label>
            </div>
          </div>
        )}
      </div>
      
      {/* External Backup */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl">
        <button
          onClick={() => setShowExternalSettings(!showExternalSettings)}
          className="flex items-center justify-between w-full p-4"
        >
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-text-muted)]">{Icons.server}</span>
            <div className="text-left">
              <span className="text-sm font-medium">{t('backup.externalBackup') || 'External Backup'}</span>
              <p className="text-2xs text-[var(--color-text-muted)]">
                {t('backup.externalBackupDesc') || 'Backup to your own server'}
              </p>
            </div>
          </div>
          <span className="text-[var(--color-text-muted)]">
            {showExternalSettings ? Icons.chevronUp : Icons.chevronDown}
          </span>
        </button>
        
        {showExternalSettings && (
          <div className="px-4 pb-4 space-y-4 border-t border-[var(--color-border)]">
            <div className="flex items-center justify-between pt-4">
              <span className="text-sm">{t('backup.enableExternal') || 'Enable External Backup'}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={schedule.external_enabled}
                  onChange={(e) => {
                    const enabled = e.target.checked
                    updateDestinationList((destinations) => {
                      if (!destinations.length) {
                        return [{ ...createEmptyDestination(1), enabled }]
                      }
                      return destinations.map((destination) => ({ ...destination, enabled }))
                    })
                  }}
                  className="sr-only peer"
                />
                <div className="w-10 h-6 bg-[var(--color-bg-secondary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]" />
              </label>
            </div>
            
            {schedule.external_enabled && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-[var(--color-text-secondary)]">
                    {t('backup.destinationCount') || 'Configured destinations'}: {schedule.external_destinations?.length || 0}
                  </span>
                  <button
                    type="button"
                    onClick={addExternalDestination}
                    className="px-3 py-1.5 rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)] text-xs font-medium hover:bg-[var(--color-accent)]/20 transition-colors"
                  >
                    + {t('backup.addDestination') || 'Add Destination'}
                  </button>
                </div>

                <div className="space-y-3">
                  {(schedule.external_destinations || []).map((destination, index) => (
                    <div key={destination.id || index} className="rounded-lg border border-[var(--color-border)] p-3 bg-[var(--color-bg-secondary)]/60 space-y-3">
                      <div className="flex items-center flex-wrap gap-2">
                        <input
                          type="text"
                          value={destination.name || ''}
                          onChange={(e) => updateExternalDestination(index, 'name', e.target.value)}
                          placeholder={`${t('backup.destinationLabel') || 'Destination'} ${index + 1}`}
                          className="flex-1 min-w-0 p-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                        />
                        <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] flex-shrink-0">
                          <input
                            type="checkbox"
                            checked={destination.enabled !== false}
                            onChange={(e) => updateExternalDestination(index, 'enabled', e.target.checked)}
                          />
                          {t('backup.enabled') || 'Enabled'}
                        </label>
                        <button
                          type="button"
                          onClick={() => removeExternalDestination(index)}
                          disabled={(schedule.external_destinations || []).length <= 1}
                          className="px-2 py-1 text-xs rounded-lg text-red-500 hover:bg-red-500/10 disabled:opacity-40 flex-shrink-0"
                        >
                          {t('backup.removeDestination') || 'Remove'}
                        </button>
                      </div>

                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => moveExternalDestination(index, -1)}
                          disabled={index === 0}
                          className="px-2 py-1 text-xs rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-40"
                        >
                          {t('backup.moveDestinationUp') || 'Move Up'}
                        </button>
                        <button
                          type="button"
                          onClick={() => moveExternalDestination(index, 1)}
                          disabled={index === (schedule.external_destinations || []).length - 1}
                          className="px-2 py-1 text-xs rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] disabled:opacity-40"
                        >
                          {t('backup.moveDestinationDown') || 'Move Down'}
                        </button>
                      </div>

                      <input
                        type="url"
                        value={destination.external_url || ''}
                        onChange={(e) => updateExternalDestination(index, 'external_url', e.target.value)}
                        placeholder="https://your-server.com/remote.php/dav/files/user"
                        className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)] placeholder-[var(--color-text-muted)]"
                      />

                      <div className="relative">
                        <input
                          type={isDestinationApiKeyVisible(destination.id || `destination_${index}`) ? 'text' : 'password'}
                          value={destination.external_api_key || ''}
                          onChange={(e) => updateExternalDestination(index, 'external_api_key', e.target.value)}
                          placeholder={destination.has_external_api_key && !destination.external_api_key ? '••••••••••• (saved)' : 'username:app-password'}
                          className="w-full p-3 pr-10 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)] placeholder-[var(--color-text-muted)]"
                        />
                        <button
                          type="button"
                          onClick={() => toggleDestinationApiKeyVisibility(destination.id || `destination_${index}`)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                          title={isDestinationApiKeyVisible(destination.id || `destination_${index}`)
                            ? (t('backup.hideCredentials') || 'Hide credentials')
                            : (t('backup.showCredentials') || 'Show credentials')}
                        >
                          {isDestinationApiKeyVisible(destination.id || `destination_${index}`)
                            ? Icons.chevronUp
                            : Icons.chevronDown}
                        </button>
                      </div>

                      <input
                        type="text"
                        value={destination.external_path || '/GearCargo'}
                        onChange={(e) => updateExternalDestination(index, 'external_path', e.target.value)}
                        placeholder="/GearCargo"
                        className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)] placeholder-[var(--color-text-muted)]"
                      />
                    </div>
                  ))}
                </div>

                <p className="text-2xs text-[var(--color-text-muted)] mt-1">
                  {t('backup.apiKeyHint') || 'For Nextcloud: username:app-password'}
                </p>

                {(schedule.external_destinations || []).length > 0 && (
                  <div>
                    <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                      {t('backup.activeDestination') || 'Active Destination for Test/Browse'}
                    </label>
                    <select
                      value={selectedExternalDestinationIndex}
                      onChange={(e) => {
                        setSelectedExternalDestinationIndex(parseInt(e.target.value, 10))
                        setExternalFolders(null)
                        setExternalFiles(null)
                      }}
                      className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                    >
                      {(schedule.external_destinations || []).map((destination, index) => (
                        <option key={destination.id || index} value={index}>
                          {destination.name || `${t('backup.destinationLabel') || 'Destination'} ${index + 1}`}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <button
                  onClick={() => {
                    const currentPath = activeDestination?.external_path || '/GearCargo'
                    const parent = currentPath.includes('/') && currentPath !== '/'
                      ? currentPath.split('/').slice(0, -1).join('/') || '/'
                      : '/'
                    browseExternalFolders(parent)
                  }}
                  disabled={browsingFolders || (!activeDestination?.external_api_key && !activeDestination?.has_external_api_key)}
                  className="w-full py-2 px-4 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {browsingFolders ? (
                    <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    Icons.folder
                  )}
                  <span>{t('backup.browseFolders') || 'Browse folders'}</span>
                </button>

                {/* Folder browser */}
                {externalFolders !== null && (
                  <div className="bg-[var(--color-bg-secondary)] rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                        {browsePath === '/' ? 'Root' : browsePath}
                      </span>
                      <div className="flex gap-2">
                        {browsePath !== '/' && (
                          <button
                            onClick={() => {
                              const parent = browsePath.split('/').slice(0, -1).join('/') || '/'
                              browseExternalFolders(parent)
                            }}
                            className="text-xs text-[var(--color-accent)] hover:underline"
                          >
                            ↑ {t('backup.parentFolder') || 'Up'}
                          </button>
                        )}
                        <button
                          onClick={() => setExternalFolders(null)}
                          className="text-xs text-[var(--color-text-muted)] hover:underline"
                        >
                          {t('common.close') || 'Close'}
                        </button>
                      </div>
                    </div>
                    {/* Select current folder button */}
                    {browsePath !== '/' && (
                      <button
                        onClick={() => {
                          updateExternalDestination(selectedExternalDestinationIndex, 'external_path', browsePath)
                          setExternalFolders(null)
                        }}
                        className="w-full py-2 px-3 rounded-lg bg-[var(--color-accent)]/10 text-[var(--color-accent)] text-xs font-medium hover:bg-[var(--color-accent)]/20 transition-colors border border-[var(--color-accent)]/30"
                      >
                        ✓ {t('backup.useThisFolder') || 'Use This Folder'}
                      </button>
                    )}
                    {externalFolders.length === 0 ? (
                      <p className="text-2xs text-[var(--color-text-muted)] italic">
                        {t('backup.noFolders') || 'No subfolders found'}
                      </p>
                    ) : (
                      <div className="space-y-1 max-h-48 overflow-y-auto">
                        {externalFolders.map((folder) => (
                          <div key={folder} className="flex items-center justify-between p-2 rounded hover:bg-[var(--color-bg-tertiary)] transition-colors">
                            <button
                              onClick={() => {
                                const newPath = browsePath === '/' ? `/${folder}` : `${browsePath}/${folder}`
                                browseExternalFolders(newPath)
                              }}
                              className="flex items-center gap-2 text-sm text-[var(--color-text-primary)] flex-1 text-left"
                            >
                              {Icons.folder}
                              <span>{folder}</span>
                            </button>
                            <button
                              onClick={() => selectExternalFolder(folder)}
                              className="text-xs text-[var(--color-accent)] hover:underline px-2"
                            >
                              {t('backup.selectFolder') || 'Select'}
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                
                <button
                  onClick={testExternalConnection}
                  disabled={testingConnection || !activeDestination?.external_url}
                  className="w-full py-2 px-4 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80 transition-colors flex items-center justify-center gap-2"
                >
                  {testingConnection ? (
                    <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    Icons.refresh
                  )}
                  <span>{t('backup.testConnection') || 'Test Connection'}</span>
                </button>

                {/* Restore from External */}
                <div className="border-t border-[var(--color-border)] pt-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                        {t('backup.restoreFromExternal') || 'Restore from External'}
                      </span>
                      <p className="text-2xs text-[var(--color-text-muted)]">
                        {t('backup.restoreFromExternalDesc') || 'Download and restore a backup from your external server'}
                      </p>
                    </div>
                    <button
                      onClick={browseExternalFiles}
                      disabled={browsingFiles || (!activeDestination?.external_api_key && !activeDestination?.has_external_api_key)}
                      className="px-3 py-2 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-secondary)]/80 transition-colors disabled:opacity-50 flex items-center gap-2"
                    >
                      {browsingFiles ? (
                        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      ) : (
                        Icons.folder
                      )}
                      <span className="text-xs">{t('backup.browseFiles') || 'Browse Files'}</span>
                    </button>
                  </div>

                  {externalFiles !== null && (
                    <div className="bg-[var(--color-bg-secondary)] rounded-lg p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                          {activeDestination?.external_path || '/GearCargo'} — {externalFiles.length} {t('backup.filesFound') || 'backup files'}
                        </span>
                        <button
                          onClick={() => setExternalFiles(null)}
                          className="text-xs text-[var(--color-text-muted)] hover:underline"
                        >
                          {t('common.close') || 'Close'}
                        </button>
                      </div>
                      {externalFiles.length === 0 ? (
                        <p className="text-2xs text-[var(--color-text-muted)] italic">
                          {t('backup.noFilesFound') || 'No .zip backup files found in this folder'}
                        </p>
                      ) : (
                        <div className="space-y-1 max-h-60 overflow-y-auto">
                          {externalFiles.map((file) => (
                            <div key={file.name} className="flex items-center justify-between p-2 rounded hover:bg-[var(--color-bg-tertiary)] transition-colors">
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-[var(--color-text-primary)] truncate">{file.name}</p>
                                <p className="text-2xs text-[var(--color-text-muted)]">
                                  {file.size_human}{file.last_modified ? ` • ${new Date(file.last_modified).toLocaleDateString()}` : ''}
                                </p>
                              </div>
                              <button
                                onClick={() => restoreFromExternal(file.name)}
                                disabled={restoringExternal}
                                className="ml-2 px-3 py-1.5 text-xs text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1"
                              >
                                {restoringExternal ? (
                                  <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                                ) : (
                                  Icons.refresh
                                )}
                                <span>{t('backup.restore') || 'Restore'}</span>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      
      {/* Advanced Settings */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl">
        <button
          onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
          className="flex items-center justify-between w-full p-4"
        >
          <span className="text-sm font-medium">{t('backup.advancedSettings') || 'Advanced Settings'}</span>
          <span className="text-[var(--color-text-muted)]">
            {showAdvancedSettings ? Icons.chevronUp : Icons.chevronDown}
          </span>
        </button>
        
        {showAdvancedSettings && (
          <div className="px-4 pb-4 space-y-4 border-t border-[var(--color-border)]">
            <div className="pt-4">
              <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                {t('backup.retentionDays') || 'Keep backups for (days)'}
              </label>
              <input
                type="number"
                value={schedule.retention_days}
                onChange={(e) => handleScheduleChange('retention_days', parseInt(e.target.value))}
                min={7}
                max={365}
                className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
              />
            </div>
            
            <div>
              <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-2">
                {t('backup.maxBackups') || 'Maximum backups to keep'}
              </label>
              <input
                type="number"
                value={schedule.max_backups}
                onChange={(e) => handleScheduleChange('max_backups', parseInt(e.target.value))}
                min={1}
                max={50}
                className="w-full p-3 rounded-lg bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
              />
            </div>
            
            <div className="flex items-center justify-between py-2">
              <span className="text-sm">{t('backup.notifyOnSuccess') || 'Notify on success'}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={schedule.notify_on_success}
                  onChange={(e) => handleScheduleChange('notify_on_success', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-10 h-6 bg-[var(--color-bg-secondary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]" />
              </label>
            </div>
            
            <div className="flex items-center justify-between py-2">
              <span className="text-sm">{t('backup.notifyOnFailure') || 'Notify on failure'}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={schedule.notify_on_failure}
                  onChange={(e) => handleScheduleChange('notify_on_failure', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-10 h-6 bg-[var(--color-bg-secondary)] peer-focus:ring-2 peer-focus:ring-[var(--color-accent)] rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[var(--color-accent)]" />
              </label>
            </div>
          </div>
        )}
      </div>
      
      {/* Stored Backups */}
      {status?.available_backups?.length > 0 && (
        <div className="bg-[var(--color-bg-tertiary)] rounded-xl">
          <button
            onClick={() => setShowBackupList(!showBackupList)}
            className="flex items-center justify-between w-full p-4"
          >
            <div className="flex items-center gap-3">
              <span className="text-[var(--color-text-muted)]">{Icons.folder}</span>
              <div className="text-left">
                <span className="text-sm font-medium">{t('backup.storedBackups') || 'Stored Backups'}</span>
                <p className="text-2xs text-[var(--color-text-muted)]">
                  {status.total_backup_count} {t('backup.backupsAvailable') || 'backups available'}
                </p>
              </div>
            </div>
            <span className="text-[var(--color-text-muted)]">
              {showBackupList ? Icons.chevronUp : Icons.chevronDown}
            </span>
          </button>
          
          {showBackupList && (
            <div className="px-4 pb-4 border-t border-[var(--color-border)]">
              <div className="space-y-2 pt-4">
                {status.available_backups.map((backup) => (
                  <div
                    key={backup.filename}
                    className="flex items-center justify-between p-3 bg-[var(--color-bg-secondary)] rounded-lg"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {backup.label || new Date(backup.created_at).toLocaleString()}
                      </p>
                      <p className="text-2xs text-[var(--color-text-muted)]">
                        {backup.size_human}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={async () => {
                          try {
                            const response = await backupApi.downloadStored(backup.filename)
                            const blob = new Blob([response.data], { type: 'application/zip' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = backup.filename
                            a.click()
                            URL.revokeObjectURL(url)
                          } catch (error) {
                            toast.error(t('backup.downloadFailed') || 'Failed to download backup')
                          }
                        }}
                        className="p-2 text-[var(--color-text-secondary)] hover:bg-[var(--color-accent)]/10 rounded-lg transition-colors"
                        title={t('backup.download') || 'Download'}
                      >
                        {Icons.download}
                      </button>
                      {schedule.external_enabled && (
                        <button
                          onClick={async () => {
                            try {
                              setSendingExternal(true)
                              const response = await backupApi.sendToExternal(backup.filename)
                              toast.success(response.data.message || 'Sent to external server')
                            } catch (error) {
                              toast.error(error.response?.data?.error || 'Failed to send to external server')
                            } finally {
                              setSendingExternal(false)
                            }
                          }}
                          disabled={sendingExternal}
                          className="p-2 text-[var(--color-text-secondary)] hover:bg-[var(--color-accent)]/10 rounded-lg transition-colors disabled:opacity-50"
                          title={t('backup.sendToExternal') || 'Send to external server'}
                        >
                          {sendingExternal ? (
                            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                          ) : (
                            Icons.cloud
                          )}
                        </button>
                      )}
                      <button
                        onClick={() => restoreBackup(backup.filename)}
                        disabled={importing}
                        className="p-2 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 rounded-lg transition-colors"
                        title={t('backup.restore') || 'Restore'}
                      >
                        {Icons.refresh}
                      </button>
                      <button
                        onClick={() => deleteBackup(backup.filename)}
                        className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors"
                        title={t('backup.delete') || 'Delete'}
                      >
                        {Icons.trash}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* Save Button */}
      <button
        onClick={saveSchedule}
        disabled={saving}
        className="w-full py-3 px-4 bg-[var(--color-accent)] text-white rounded-xl font-medium hover:bg-[var(--color-accent)]/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {saving ? (
          <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
        ) : (
          t('backup.saveSettings') || 'Save Backup Settings'
        )}
      </button>
      
      {/* Backup Now Button */}
      <button
        onClick={runBackupNow}
        disabled={backing}
        className="w-full py-3 px-4 bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] rounded-xl font-medium hover:bg-[var(--color-bg-tertiary)]/80 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {backing ? (
          <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <>
            {Icons.cloud}
            <span>{t('backup.backupNow') || 'Backup Now'}</span>
          </>
        )}
      </button>

      {/* Send to External Button - only show when external is configured */}
      {schedule.external_enabled && status?.available_backups?.length > 0 && (
        <button
          onClick={async () => {
            try {
              setSendingExternal(true)
              const response = await backupApi.sendToExternal()
              toast.success(response.data.message || 'Latest backup sent to external server')
            } catch (error) {
              toast.error(error.response?.data?.error || 'Failed to send to external server')
            } finally {
              setSendingExternal(false)
            }
          }}
          disabled={sendingExternal}
          className="w-full py-3 px-4 bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] rounded-xl font-medium hover:bg-[var(--color-bg-tertiary)]/80 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {sendingExternal ? (
            <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              {Icons.server}
              <span>{t('backup.sendToExternal') || 'Send Latest to External'}</span>
            </>
          )}
        </button>
      )}
      
      {/* Info Box */}
      <div className="bg-blue-500/10 rounded-xl p-4">
        <p className="text-xs text-blue-600 dark:text-blue-400">
          <strong>{t('backup.infoTitle') || 'About Backups'}:</strong>{' '}
          {t('backup.infoText') || 'Backups include all your vehicles, fuel logs, service records, repairs, taxes, reminders, and uploaded attachments. You can restore from any backup at any time.'}
        </p>
      </div>
    </div>
  )
}
