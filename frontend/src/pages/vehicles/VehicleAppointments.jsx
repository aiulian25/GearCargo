import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useFieldArray, useForm } from 'react-hook-form'
import toast from 'react-hot-toast'
import { appointmentApi, vehicleApi, serviceApi, repairApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { useMutationIntent } from '../../hooks/useMutationIntent'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { mutationOptions } from '../../utils/mutationProtocol'
import { isOfflineWriteError, announceOfflineSaved } from '../../utils/offlineWrite'
import { appointmentTime } from '../../utils/appointmentTime'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import FormField from '../../components/ui/FormField'
import { SkeletonList } from '../../components/ui/Skeleton'
import EmptyState from '../../components/ui/EmptyState'

const TARGETS = ['reminder_id', 'todo_id', 'service_id', 'prediction_id']
function VisitForm({ record, vehicle, work, expenses, completing, onSaved, onClose }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const intent = useMutationIntent()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { register, control, getValues, handleSubmit, formState: { isDirty } } = useForm({ defaultValues: completing ? { entry_ids: [], resolved_task_ids: [], no_cost: false } : {
    title: record?.title || '', shop_name: record?.shop_name || '', shop_contact: record?.shop_contact || '', notes: record?.notes || '',
    time_zone: record?.time_zone || user?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
    start_local: record?.start_local || '', end_local: record?.end_local || '', start_fold: record?.start_fold ?? '', end_fold: record?.end_fold ?? '',
    prepare_minutes: record?.prepare_minutes ?? 1440, notify_push: record?.notify_push || false, notify_email: record?.notify_email || false,
    tasks: record?.tasks || [],
  } })
  const { fields, append, remove } = useFieldArray({ control, name: 'tasks', keyName: 'formKey' })
  const markSaved = useUnsavedChanges(isDirty)
  useEffect(() => { if (record) intent.capture(record) }, [record, intent])
  const field = (name, type = 'text', props = {}) => <FormField id={`visit-${name}`} label={t(`appointments.${name}`)}>
    <input id={`visit-${name}`} className="input w-full" type={type} {...register(name)} {...props} />
  </FormField>
  const submit = async data => {
    setBusy(true); setError('')
    try {
      let result
      if (completing) result = await appointmentApi.action(record.id, 'complete', {
        entry_ids: (data.entry_ids || []).map(Number), resolved_task_ids: (data.resolved_task_ids || []).map(Number), no_cost: data.no_cost,
      }, intent.options())
      else {
        const payload = { ...data, vehicle_id: vehicle.id, prepare_minutes: Number(data.prepare_minutes),
          start_fold: data.start_fold === '' ? null : Number(data.start_fold), end_fold: data.end_fold === '' ? null : Number(data.end_fold) }
        result = record ? await appointmentApi.update(record.id, payload, intent.options()) : await appointmentApi.create(payload, intent.options())
      }
      markSaved(); onSaved(result.data); toast.success(t('appointments.saved'))
    } catch (err) {
      if (isOfflineWriteError(err)) { markSaved(); announceOfflineSaved(t); onSaved(null); return }
      const key = err.response?.data?.message_key
      setError(err.response?.status === 409 ? t('appointments.conflict') : t(key?.startsWith('appointments.') ? key : 'appointments.invalid'))
    } finally { setBusy(false) }
  }
  return <form className="card p-4 space-y-4" aria-label={t(completing ? 'appointments.complete' : 'appointments.details')} onSubmit={handleSubmit(submit)}>
    <h2 className="font-semibold">{t(completing ? 'appointments.complete' : 'appointments.details')}</h2>
    {completing ? <>
      <p>{t('appointments.expenseHint')}</p>
      <div className="flex flex-wrap gap-3">{['service', 'repair'].map(kind => <Link key={kind} className="underline" to={`/vehicles/${vehicle.id}/${kind}/add`} state={{ workshopReturnTo: `/vehicles/${vehicle.id}/appointments` }}>{t(`appointments.add_${kind}`)}</Link>)}</div>
      {expenses.map(entry => <label key={entry.id} className="flex gap-2 items-start"><input type="checkbox" value={entry.id} {...register('entry_ids')} /><span>{entry.title || entry.type} · {entry.date} · {entry.amount} {entry.currency}</span></label>)}
      <label className="flex gap-2"><input type="checkbox" {...register('no_cost')} />{t('appointments.no_cost')}</label>
      <fieldset className="space-y-2"><legend className="font-semibold">{t('appointments.resolveWork')}</legend><p className="text-sm text-(--color-text-muted)">{t('appointments.resolveHint')}</p>
        {record.tasks.filter(task => !task.done).map(task => <label key={task.id} className="flex gap-2"><input type="checkbox" value={task.id} {...register('resolved_task_ids')} />{task.title}</label>)}
      </fieldset>
    </> : <>
      {field('title', 'text', { required: true, maxLength: 255 })}
      {field('shop_name', 'text', { maxLength: 100 })}{field('shop_contact', 'text', { maxLength: 255 })}
      <p className="text-sm text-(--color-text-muted)">{t('appointments.manualHint')}</p>
      {field('time_zone', 'text', { required: true, placeholder: 'Europe/London' })}
      <div className="grid sm:grid-cols-2 gap-3">{field('start_local', 'datetime-local', { required: true })}{field('end_local', 'datetime-local', { required: true })}</div>
      <details><summary>{t('appointments.dstChoices')}</summary><p className="text-sm mt-2">{t('appointments.dstHint')}</p>
        <div className="grid sm:grid-cols-2 gap-3">{['start_fold', 'end_fold'].map(name => <FormField key={name} id={`visit-${name}`} label={t(`appointments.${name}`)}>
          <select id={`visit-${name}`} className="input w-full" {...register(name)}><option value="">{t('appointments.chooseIfRepeated')}</option><option value="0">{t('appointments.earlier')}</option><option value="1">{t('appointments.later')}</option></select>
        </FormField>)}</div>
      </details>
      {field('prepare_minutes', 'number', { min: 0, max: 43200, required: true })}
      <p className="text-sm text-(--color-text-muted)">{t('appointments.preparationHint')}</p>
      <div className="flex flex-wrap gap-4">{['notify_push', 'notify_email'].map(name => <label key={name} className="flex gap-2"><input type="checkbox" {...register(name)} />{t(`appointments.${name}`)}</label>)}</div>
      <fieldset className="space-y-3"><legend className="font-semibold">{t('appointments.checklist')}</legend>
        {fields.map((task, index) => <div key={task.formKey} className="flex gap-2 items-center">
          <input type="checkbox" disabled={TARGETS.some(key => task[key])} aria-label={`${t('appointments.prepared')}: ${task.title}`} {...register(`tasks.${index}.done`)} />
          <input className="input min-w-0 flex-1" aria-label={`${t('appointments.task')} ${index + 1}`} required maxLength={255} {...register(`tasks.${index}.title`)} />
          <button type="button" className="text-sm underline" onClick={() => remove(index)}>{t('common.delete')}</button>
        </div>)}
        <button type="button" className="btn btn-secondary" onClick={() => append({ title: '', done: false })}>{t('appointments.addTask')}</button>
        {work.length > 0 && <div className="space-y-2"><p>{t('appointments.linkWork')}</p>{work.map((item, index) => <button key={index} type="button" className="btn btn-secondary block" onClick={() => {
          if (!getValues('tasks').some(task => TARGETS.some(key => item[key] && item[key] === task[key]))) append({ ...item, done: false })
        }}>{item.title}</button>)}</div>}
      </fieldset>
      <FormField id="visit-notes" label={t('appointments.notes')}><textarea id="visit-notes" className="input w-full" maxLength={10000} {...register('notes')} /></FormField>
      {!record && <p className="text-sm text-(--color-text-muted)">{t('appointments.offlineHint')}</p>}
    </>}
    {error && <p role="alert" className="text-red-500">{error}</p>}
    <div className="flex gap-3"><button className="btn btn-primary" type="submit" disabled={busy}>{t(completing ? 'appointments.complete' : 'common.save')}</button><button className="btn btn-secondary" type="button" disabled={busy} onClick={onClose}>{t('common.cancel')}</button></div>
  </form>
}

export default function VehicleAppointments() {
  const { id } = useParams()
  const { t, language } = useTranslation()
  const confirm = useConfirm()
  const actionKeys = useRef({})
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    setLoading(true); setError(false)
    try {
      const [vehicle, visits, work] = await Promise.all([vehicleApi.getById(id), appointmentApi.list(id), appointmentApi.work(id)])
      const expenses = []
      for (const api of [serviceApi, repairApi]) {
        let page = 1, response
        do { response = await api.getByVehicle(id, page++); expenses.push(...response.data.entries) } while (page <= response.data.pages)
      }
      setData({ vehicle: vehicle.data, visits: visits.data.appointments, work: work.data.work, expenses })
    } catch { setError(true) } finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const refresh = event => { if (!form && ['SYNC_SUCCESS', 'SYNC_COMPLETE'].includes(event.data?.type)) load() }
    navigator.serviceWorker?.addEventListener('message', refresh)
    return () => navigator.serviceWorker?.removeEventListener('message', refresh)
  }, [load, form])
  const saved = visit => { setForm(null); if (visit) setData(prev => ({ ...prev, visits: prev.visits.some(v => v.id === visit.id) ? prev.visits.map(v => v.id === visit.id ? visit : v) : [visit, ...prev.visits] })) }
  const close = async () => { if (await confirm({ title: t('appointments.discard'), message: t('appointments.discardHint'), destructive: true })) setForm(null) }
  const action = async (visit, kind) => {
    if (!await confirm({ title: t(`appointments.${kind}`), message: t(`appointments.${kind}Hint`), destructive: kind === 'cancel' })) return
    setBusy(true)
    try {
      const key = `${visit.id}-${visit.revision}-${kind}`
      actionKeys.current[key] ||= crypto.randomUUID()
      saved((await appointmentApi.action(visit.id, kind, kind === 'confirm' ? { arranged_externally: true } : {}, mutationOptions(visit, actionKeys.current[key]))).data)
    } catch { toast.error(t('appointments.conflict')) } finally { setBusy(false) }
  }
  return <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
    <Link className="underline text-sm" to={`/vehicles/${id}/alerts`}>{t('common.back')}</Link>
    <div className="flex justify-between gap-3"><div><h1 className="text-xl font-semibold">{t('appointments.heading')}</h1><p className="text-sm text-(--color-text-muted)">{data?.vehicle.name}</p></div>
      {data && !data.vehicle.archived && !form && <button className="btn btn-primary" onClick={() => setForm({})}>{t('appointments.plan')}</button>}</div>
    <p className="text-sm text-(--color-text-muted)">{t('appointments.manualHint')}</p>
    {!form && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={load}>{t('appointments.refresh')}</button>}
    {loading ? <SkeletonList rows={3} /> : error ? <p role="alert">{t('appointments.loadError')}</p> : <>
      {data.vehicle.archived && <p>{t('appointments.archived')}</p>}
      {form && <VisitForm key={`${form.record?.id || 'new'}-${!!form.completing}`} {...form} vehicle={data.vehicle} work={data.work} expenses={data.expenses} onSaved={saved} onClose={close} />}
      {!data.visits.length && !form && <EmptyState title={t('appointments.empty')} description={t('appointments.manualHint')} />}
      {data.visits.map(visit => <article key={visit.id} className="card p-4 space-y-3">
        <div className="flex justify-between gap-3"><h2 className="font-semibold">{visit.title}</h2><span className="text-sm">{t(`appointments.${visit.status}`)}</span></div>
        <p>{appointmentTime(visit.start_at, visit.time_zone, language)} → {appointmentTime(visit.end_at, visit.time_zone, language)} <span className="text-sm">({visit.time_zone})</span></p>
        {visit.shop_name && <p>{visit.shop_name}</p>}{visit.shop_contact && <p className="break-words">{visit.shop_contact}</p>}
        {visit.notes && <p className="whitespace-pre-wrap break-words">{visit.notes}</p>}
        {visit.dropoff_at && <p>{t('appointments.droppedOff')}: {appointmentTime(visit.dropoff_at, visit.time_zone, language)}</p>}
        {visit.pickup_at && <p>{t('appointments.pickedUp')}: {appointmentTime(visit.pickup_at, visit.time_zone, language)}</p>}
        {visit.tasks.length > 0 && <ul className="space-y-1">{visit.tasks.map(task => <li key={task.id}>{task.done ? '✓ ' : '○ '}{task.title}</li>)}</ul>}
        {visit.expenses.map(expense => <Link key={expense.id} className="block underline" to={`/vehicles/${id}/${expense.type}/add?edit=${expense.entry_id}`}>{expense.title || expense.type} · {expense.amount} {expense.currency} · {t('appointments.linkedOnce')}</Link>)}
        {!data.vehicle.archived && !form && !['completed', 'cancelled'].includes(visit.status) && <div className="flex flex-wrap gap-2">
          <button className="btn btn-secondary" disabled={busy} onClick={() => setForm({ record: visit })}>{t('common.edit')}</button>
          {visit.status === 'requested' && <button className="btn btn-secondary" disabled={busy} onClick={() => action(visit, 'confirm')}>{t('appointments.confirm')}</button>}
          {visit.status === 'confirmed' && !visit.dropoff_at && <button className="btn btn-secondary" disabled={busy} onClick={() => action(visit, 'dropoff')}>{t('appointments.dropoff')}</button>}
          {visit.status === 'confirmed' && visit.dropoff_at && <button className="btn btn-primary" disabled={busy} onClick={() => setForm({ record: visit, completing: true })}>{t('appointments.complete')}</button>}
          <button className="btn btn-secondary" disabled={busy} onClick={() => action(visit, 'cancel')}>{t('appointments.cancel')}</button>
        </div>}
      </article>)}
    </>}
  </div>
}
