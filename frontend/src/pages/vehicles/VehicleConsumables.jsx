import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { vehicleApi, consumableApi } from '../../services/api'
import { useTranslation, useCurrency } from '../../contexts/LanguageContext'
import { formatDate } from '../../utils/dateFormat'
import { Skeleton, SkeletonList } from '../../components/ui/Skeleton'
import EmptyState from '../../components/ui/EmptyState'

const Icons = {
  back: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  ),
  plus: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  ),
  edit: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  ),
  trash: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  ),
  gauge: (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a10 10 0 1 0 10 10" /><path d="M12 12l4-4" /><circle cx="12" cy="12" r="1" />
    </svg>
  ),
}

// status -> tailwind colour classes (bar + text). Kept in one place.
const STATUS_STYLE = {
  good: { bar: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  monitor: { bar: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
  replace: { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
  unknown: { bar: 'bg-gray-400', text: 'text-[var(--color-text-muted)]' },
}

export default function VehicleConsumables() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { formatCurrency } = useCurrency()

  const [vehicle, setVehicle] = useState(null)
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  const distanceUnit = vehicle?.distance_unit === 'miles' ? (t('common.miles') || 'mi') : (t('common.km') || 'km')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [vRes, cRes] = await Promise.all([
        vehicleApi.getById(id),
        consumableApi.getByVehicle(id),
      ])
      setVehicle(vRes.data)
      setEntries(cRes.data?.entries || [])
    } catch (err) {
      console.error('Failed to load consumables:', err)
      toast.error(t('consumables.loadError') || 'Failed to load consumables')
    } finally {
      setLoading(false)
    }
  }, [id, t])

  useEffect(() => { load() }, [load])

  const handleDelete = async (entry) => {
    const label = t(`consumableTypes.${entry.consumable_type}`) || entry.consumable_type
    if (!window.confirm((t('consumables.deleteConfirm') || 'Delete this {item} entry?').replace('{item}', label))) return
    try {
      await consumableApi.delete(entry.id)
      setEntries((prev) => prev.filter((e) => e.id !== entry.id))
      toast.success(t('consumables.deleted') || 'Consumable deleted')
    } catch (err) {
      console.error('Delete failed:', err)
      toast.error(t('common.error') || 'Error')
    }
  }

  const statusLabel = (status) => ({
    good: t('consumables.statusGood') || 'Good',
    monitor: t('consumables.statusMonitor') || 'Monitor',
    replace: t('consumables.statusReplace') || 'Replace soon',
    unknown: t('consumables.statusUnknown') || 'No estimate',
  }[status] || status)

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-5">
          <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32 rounded" />
            <Skeleton className="h-3 w-20 rounded" />
          </div>
          <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
        </div>
        <SkeletonList rows={4} />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate(`/vehicles/${id}`)} className="btn-icon shrink-0" aria-label={t('common.back') || 'Back'}>
            {Icons.back}
          </button>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold truncate">{t('consumables.title') || 'Consumables'}</h1>
            {vehicle && <p className="text-2xs text-[var(--color-text-muted)] truncate">{vehicle.name}</p>}
          </div>
        </div>
        <Link
          to={`/vehicles/${id}/consumable/add`}
          className="btn-primary flex items-center gap-1.5 shrink-0"
        >
          {Icons.plus}<span className="hidden sm:inline">{t('consumables.add') || 'Add'}</span>
        </Link>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          icon={Icons.gauge}
          title={t('consumables.emptyTitle') || 'No consumables tracked yet'}
          description={t('consumables.emptyDesc') || 'Track tyres, battery, wipers and filters to estimate wear and plan replacements.'}
          actionLabel={t('consumables.addFirst') || 'Add your first consumable'}
          actionTo={`/vehicles/${id}/consumable/add`}
        />
      ) : (
        <ul className="space-y-3">
          {entries.map((entry) => {
            const wear = entry.wear || { status: 'unknown', wear_percent: null }
            const style = STATUS_STYLE[wear.status] || STATUS_STYLE.unknown
            const pct = wear.wear_percent
            const barWidth = pct === null ? 0 : Math.min(100, Math.max(0, pct))
            const typeLabel = t(`consumableTypes.${entry.consumable_type}`) || entry.consumable_type
            return (
              <li key={entry.id} className="card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-sm truncate">
                      {typeLabel}
                      {entry.quantity > 1 && <span className="text-[var(--color-text-muted)]"> ×{entry.quantity}</span>}
                    </p>
                    <p className="text-2xs text-[var(--color-text-muted)] truncate">
                      {entry.brand ? `${entry.brand} · ` : ''}{formatDate(entry.date)}
                      {entry.install_odometer != null && ` · ${entry.install_odometer.toLocaleString()} ${distanceUnit}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-sm font-semibold mr-1">{formatCurrency(entry.amount)}</span>
                    <button
                      onClick={() => navigate(`/vehicles/${id}/consumable/add?edit=${entry.id}`)}
                      className="btn-icon" aria-label={t('common.edit') || 'Edit'}
                    >{Icons.edit}</button>
                    <button
                      onClick={() => handleDelete(entry)}
                      className="btn-icon text-red-500" aria-label={t('common.delete') || 'Delete'}
                    >{Icons.trash}</button>
                  </div>
                </div>

                {/* Wear estimate */}
                <div className="mt-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-2xs font-medium ${style.text}`}>
                      {statusLabel(wear.status)}
                      {pct !== null && ` · ${pct}%`}
                    </span>
                    {wear.remaining_km != null && wear.remaining_km > 0 && (
                      <span className="text-2xs text-[var(--color-text-muted)]">
                        {(t('consumables.remainingKm') || '{km} {unit} left')
                          .replace('{km}', wear.remaining_km.toLocaleString())
                          .replace('{unit}', distanceUnit)}
                      </span>
                    )}
                  </div>
                  <div
                    className="h-2 rounded-full bg-[var(--color-bg-tertiary)] overflow-hidden"
                    role="progressbar"
                    aria-valuenow={pct === null ? undefined : Math.round(pct)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${typeLabel} ${statusLabel(wear.status)}`}
                  >
                    {pct !== null && <div className={`h-full ${style.bar} transition-all`} style={{ width: `${barWidth}%` }} />}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
