import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import { vehicleApi, consumableApi, tireApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useDateFormat } from '../../hooks/useDateFormat'
import { useMutationIntent } from '../../hooks/useMutationIntent'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { mutationOptions } from '../../utils/mutationProtocol'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import FormField from '../../components/ui/FormField'
import EmptyState from '../../components/ui/EmptyState'
import { SkeletonList } from '../../components/ui/Skeleton'
import { localDate } from '../../utils/dateFormat'

const POSITIONS = ['FL', 'FR', 'RL', 'RR']

function TireForm({ mode, record, event, vehicle, purchases, onSaved, onClose, onQueued }) {
  const { t } = useTranslation()
  const mutation = useMutationIntent()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const defaults = mode === 'set' ? {
    name: record?.name || '', season: record?.season || 'all_season', storage_location: record?.storage_location || '',
    tires: ['A', 'B', 'C', 'D'], purchase_entry_id: record?.purchase_entry_id || '',
    rotation_interval: record?.rotation_interval ?? '', tread_unit: record?.tread_unit || 'mm', tread_threshold: record?.tread_threshold ?? '',
  } : mode === 'reading' ? { date: localDate(), tire_id: record.tires[0].id, depth: '', unit: record.tread_unit }
    : { date: event?.date || localDate(), odometer: event?.odometer ?? vehicle.current_mileage ?? '', positions: event?.positions || record.positions }
  const { register, handleSubmit, watch, formState: { isDirty } } = useForm({ defaultValues: defaults })
  const markSaved = useUnsavedChanges(isDirty)
  useEffect(() => { if (record) mutation.capture(record) }, [record, mutation])
  const field = (name, type = 'text', props = {}) => (
    <FormField id={`tire-${name}`} label={t(`tires.${name}`)}>
      <input id={`tire-${name}`} className="input w-full" type={type} {...register(name)} {...props} />
    </FormField>
  )
  const select = (name, options) => <FormField id={`tire-${name}`} label={t(`tires.${name}`)}>
    <select id={`tire-${name}`} className="input w-full" {...register(name)}>{options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
  </FormField>
  const submit = async data => {
    setBusy(true); setError('')
    try {
      let response
      if (mode === 'set') {
        const payload = { ...data, vehicle_id: vehicle.id, purchase_entry_id: data.purchase_entry_id ? Number(data.purchase_entry_id) : null }
        response = record ? await tireApi.update(record.id, payload, mutation.options()) : await tireApi.create(payload, mutation.options())
      } else if (mode === 'reading') {
        response = await tireApi.reading(record.id, { ...data, tire_id: Number(data.tire_id) }, mutation.options())
      } else if (mode === 'correct') {
        response = await tireApi.correctEvent(record.id, event.id, { date: data.date, odometer: data.odometer }, mutation.options())
      } else {
        const positions = mode === 'remove' ? record.positions : data.positions
        if (new Set(Object.values(positions)).size !== 4) { setError(t('tires.positionsError')); return }
        response = await tireApi.event(record.id, { ...data, positions, kind: mode }, mutation.options())
      }
      markSaved(); onSaved(response.data); toast.success(t('tires.saved'))
    } catch (err) {
      if (isOfflineWriteError(err)) { markSaved(); announceOfflineSaved(t); onQueued(); return }
      setError(err.response?.status === 409 ? t('tires.conflict') : t('tires.invalid'))
    } finally { setBusy(false) }
  }
  return <form onSubmit={handleSubmit(submit)} className="card p-4 space-y-4" aria-label={t(`tires.${mode}`)}>
    <h2 className="font-semibold">{t(`tires.${mode}`)}</h2>
    {mode === 'set' ? <>
      {field('name', 'text', { required: true, maxLength: 100 })}
      {select('season', ['summer', 'winter', 'all_season'].map(v => [v, t(`tires.${v}`)]))}
      {field('storage_location', 'text', { maxLength: 200 })}
      {!record && <fieldset><legend className="text-sm mb-2">{t('tires.identities')}</legend><div className="grid grid-cols-2 gap-3">
        {POSITIONS.map((position, index) => <FormField key={position} id={`identity-${position}`} label={t(`tires.${position}`)}>
          <input id={`identity-${position}`} className="input w-full" required maxLength={60} {...register(`tires.${index}`)} />
        </FormField>)}
      </div></fieldset>}
      {select('purchase_entry_id', [['', t('tires.noPurchase')], ...purchases.map(p => [p.id, `${p.title || t('tires.purchase')} · ${p.amount} ${p.currency || ''}`])])}
      <p className="text-sm text-(--color-text-muted)">{t('tires.purchaseHint')} <Link className="text-primary-500 underline" to={`/vehicles/${vehicle.id}/consumable/add`}>{t('tires.recordPurchase')}</Link></p>
      {field('rotation_interval', 'number', { min: 0.001, max: 100000000, step: 'any', placeholder: vehicle.distance_unit })}
      {select('tread_unit', [['mm', 'mm'], ['32nds', t('tires.unit32')]])}
      {field('tread_threshold', 'number', { min: 0, max: 100, step: '0.0001' })}
      <p className="text-sm text-(--color-text-muted)">{t('tires.thresholdHint')}</p>
    </> : <>
      {field('date', 'date', { required: true, max: localDate() })}
      {mode === 'reading' ? <>
        {select('tire_id', record.tires.map(tire => [tire.id, tire.identifier]))}
        {field('depth', 'number', { required: true, min: 0, max: 100, step: '0.0001' })}
        {select('unit', [['mm', 'mm'], ['32nds', t('tires.unit32')]])}
        <p className="text-sm text-(--color-text-muted)">{t('tires.offlineHint')}</p>
      </> : <>
        {field('odometer', 'number', { min: 0, max: 100000000, step: 'any', placeholder: vehicle.distance_unit })}
        <p className="text-sm text-(--color-text-muted)">{t('tires.odometerHint')} ({vehicle.distance_unit})</p>
        {mode !== 'correct' && <fieldset><legend className="text-sm mb-2">{t('tires.positionPreview')}</legend><div className="grid grid-cols-2 gap-3">
          {POSITIONS.map(position => <FormField key={position} id={`position-${position}`} label={t(`tires.${position}`)}>
            <select id={`position-${position}`} className="input w-full" disabled={mode === 'remove'} {...register(`positions.${position}`)}>
              {record.tires.map(tire => <option key={tire.id} value={tire.identifier}>{tire.identifier}</option>)}
            </select>
          </FormField>)}
        </div><p className="text-sm mt-2">{POSITIONS.map(p => `${t(`tires.${p}`)}: ${watch(`positions.${p}`)}`).join(' · ')}</p></fieldset>}
      </>}
    </>}
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <div className="flex gap-3"><button className="btn btn-primary" disabled={busy} type="submit">{t('common.save')}</button>
      <button className="btn btn-secondary" disabled={busy} type="button" onClick={onClose}>{t('common.cancel')}</button></div>
  </form>
}

export default function VehicleTires() {
  const { id } = useParams()
  const { t } = useTranslation()
  const { formatDate } = useDateFormat()
  const confirm = useConfirm()
  const [vehicle, setVehicle] = useState(null)
  const [sets, setSets] = useState([])
  const [purchases, setPurchases] = useState([])
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const load = useCallback(async () => {
    setLoading(true); setError(false)
    try {
      const [v, list] = await Promise.all([vehicleApi.getById(id), tireApi.list(id)])
      let page = 1, rows = [], response
      do { response = await consumableApi.getByVehicle(id, page++); rows.push(...(response.data.entries || [])) } while (page <= response.data.pages)
      setVehicle(v.data); setSets(list.data.sets); setPurchases(rows)
    } catch { setError(true) } finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const refreshed = event => {
      if (!form && ['SYNC_SUCCESS', 'SYNC_COMPLETE'].includes(event.data?.type)) load()
    }
    navigator.serviceWorker?.addEventListener('message', refreshed)
    return () => navigator.serviceWorker?.removeEventListener('message', refreshed)
  }, [load, form])
  const saved = data => { setSets(prev => prev.some(s => s.id === data.id) ? prev.map(s => s.id === data.id ? data : s) : [...prev, data]); setForm(null) }
  const remove = async (record, kind, childId) => {
    if (!await confirm({ title: t('tires.confirmDelete'), message: t('tires.confirmDeleteHint'), destructive: true })) return
    try {
      const response = kind === 'event' ? await tireApi.undoEvent(record.id, childId, mutationOptions(record))
        : kind === 'reading' ? await tireApi.deleteReading(record.id, childId, mutationOptions(record)) : await tireApi.delete(record.id, mutationOptions(record))
      if (kind === 'set') setSets(prev => prev.filter(s => s.id !== record.id)); else saved(response.data)
    } catch { toast.error(t('tires.conflict')) }
  }
  const close = async () => {
    if (await confirm({ title: t('tires.discard'), message: t('tires.discardHint'), destructive: true })) setForm(null)
  }
  return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
    <Link className="text-sm underline" to={`/vehicles/${id}/consumables`}>{t('common.back')}</Link>
    <div className="flex items-start justify-between gap-3"><div><h1 className="text-xl font-semibold">{t('tires.title')}</h1><p className="text-sm text-(--color-text-muted)">{vehicle?.name}</p></div>
      {vehicle && !vehicle.archived && !form && <button className="btn btn-primary" onClick={() => setForm({ mode: 'set' })}>{t('tires.addSet')}</button>}</div>
    {!form && !loading && <button className="btn btn-secondary btn-sm" onClick={load}>{t('tires.refresh')}</button>}
    <p className="text-sm text-(--color-text-muted)">{t('tires.intro')}</p>
    {loading ? <SkeletonList rows={3} /> : error ? <div role="alert"><p>{t('tires.loadError')}</p><button className="btn btn-secondary mt-2" onClick={load}>{t('common.retry')}</button></div> : <>
      {vehicle.archived && <p>{t('tires.archived')}</p>}
      {form && <TireForm key={`${form.mode}-${form.record?.id || 'new'}-${form.event?.id || ''}`} {...form} vehicle={vehicle} purchases={purchases} onSaved={saved} onClose={close} onQueued={() => setForm(null)} />}
      {!sets.length && !form && <EmptyState title={t('tires.empty')} description={t('tires.intro')} />}
      {sets.map(record => <article key={record.id} className="card p-4 space-y-4">
        <div className="flex justify-between gap-3"><div><h2 className="font-semibold">{record.name}</h2><p className="text-sm">{t(`tires.${record.season}`)} · {t(`tires.${record.installed ? 'installed' : 'stored'}`)}</p></div>
          {!vehicle.archived && !form && <button className="btn btn-secondary" onClick={() => setForm({ mode: 'set', record })}>{t('common.edit')}</button>}</div>
        <div className="grid grid-cols-2 gap-3">{POSITIONS.map(position => <div key={position} className="rounded-lg bg-(--color-bg-tertiary) p-3"><p className="text-xs text-(--color-text-muted)">{t(`tires.${position}`)}</p><p className="font-medium">{record.positions[position]}</p></div>)}</div>
        <p>{t('tires.distance')}: {Number(record.known_distance).toLocaleString()} {record.distance_unit}{record.unknown_intervals > 0 && <span> · {t('tires.unknownDistance')}</span>}</p>
        {record.storage_location && <p>{t('tires.storage_location')}: {record.storage_location}</p>}
        {record.purchase && <p>{t('tires.purchase')}: {record.purchase.title || t('tires.purchase')} · {record.purchase.amount} {record.purchase.currency} <span className="text-sm">({t('tires.linkedOnly')})</span></p>}
        {record.rotation_remaining != null && <p>{t('tires.rotationRemaining')}: {Math.max(0, record.rotation_remaining).toLocaleString()} {record.distance_unit}</p>}
        {record.tread_threshold != null && <p>{t('tires.tread_threshold')}: {record.tread_threshold} {record.tread_unit === 'mm' ? 'mm' : t('tires.unit32')}</p>}
        {record.alerts.map(alert => <p key={alert} className="text-amber-600 dark:text-amber-400">{t(`tires.${alert}Alert`)}</p>)}
        {!vehicle.archived && !form && <div className="flex flex-wrap gap-2">
          {(record.installed ? ['rotate', 'remove'] : ['install']).map(mode => <button key={mode} className="btn btn-secondary" onClick={() => setForm({ mode, record })}>{t(`tires.${mode}`)}</button>)}
          <button className="btn btn-secondary" onClick={() => setForm({ mode: 'reading', record })}>{t('tires.reading')}</button>
          <Link className="btn btn-secondary" to={`/vehicles/${id}/reminder/add?type=tire_rotation${record.rotation_remaining != null ? `&due_mileage=${Math.ceil(vehicle.current_mileage + Math.max(0, record.rotation_remaining))}` : ''}`}>{t('tires.reminder')}</Link>
          {!record.events.length && !record.readings.length && <button className="btn btn-secondary" onClick={() => remove(record, 'set')}>{t('common.delete')}</button>}
        </div>}
        <details><summary className="cursor-pointer font-medium">{t('tires.history')}</summary><ul className="mt-3 space-y-3">{record.events.map(event => <li key={event.id} className="border-b border-(--color-border) pb-2">
          <p>{formatDate(event.date)} · {t(`tires.${event.kind}`)} · {event.odometer ?? t('tires.unknown')} {record.distance_unit}</p>
          <p className="text-xs text-(--color-text-muted)">{POSITIONS.map(p => `${t(`tires.${p}`)}: ${event.positions[p]}`).join(' · ')}</p>
          {!vehicle.archived && !form && <div className="flex gap-3"><button className="text-sm underline" onClick={() => setForm({ mode: 'correct', record, event })}>{t('tires.correct')}</button>
            {event.id === record.events.at(-1).id && <button className="text-sm underline" onClick={() => remove(record, 'event', event.id)}>{t('tires.undo')}</button>}</div>}
        </li>)}</ul></details>
        <details><summary className="cursor-pointer font-medium">{t('tires.readings')}</summary><ul className="mt-3 space-y-2">{record.readings.map(reading => <li key={reading.id} className="flex flex-wrap justify-between gap-2">
          <span>{formatDate(reading.date)} · {record.tires.find(tire => tire.id === reading.tire_id)?.identifier} · {Number(reading.depth).toLocaleString()} {reading.unit === 'mm' ? 'mm' : t('tires.unit32')}</span>
          {!vehicle.archived && !form && <button className="text-sm underline" onClick={() => remove(record, 'reading', reading.id)}>{t('common.delete')}</button>}
        </li>)}</ul></details>
      </article>)}
    </>}
  </div>
}
