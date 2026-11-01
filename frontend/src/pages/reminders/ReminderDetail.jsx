import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { reminderApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { mutationOptions } from '../../utils/mutationProtocol'
import { reminderPath } from '../../utils/reminderRoutes'

export default function ReminderDetail() {
  const { reminderId } = useParams()
  // A new notification ID gets independent state, including pending actions.
  return <ReminderRecord key={reminderId} id={reminderId} />
}

function ReminderRecord({ id }) {
  const { t } = useTranslation()
  const [reminder, setReminder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const heading = useRef(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    setReminder(null)
    if (!reminderPath(id)) {
      setError('unavailable')
      setLoading(false)
      return
    }
    reminderApi.get(id).then(({ data }) => {
      if (active) setReminder(data)
    }).catch(err => {
      if (active) setError([403, 404, 410].includes(err.response?.status) ? 'unavailable' : 'loadFailed')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id, attempt])

  useEffect(() => { if (!loading) heading.current?.focus() }, [loading])

  async function act(action) {
    setBusy(true)
    setError(null)
    try {
      let response
      if (action === 'snooze') {
        response = await reminderApi.snooze(reminder.id, 7, mutationOptions(reminder))
      } else {
        try {
          response = await reminderApi.complete(reminder.id, null, mutationOptions(reminder))
        } catch (err) {
          const data = err.response?.data
          if (data?.code !== 'MILEAGE_RECURRENCE_REQUIRED') throw err
          const answer = window.prompt(t('reminderDelivery.nextMileagePrompt')
            .replace('{minimum}', String(data.minimum_next_mileage))
            .replace('{unit}', reminder.vehicle_distance_unit || 'km'))
          if (answer === null) return
          const value = Number(answer)
          if (!Number.isInteger(value) || value < data.minimum_next_mileage) {
            setError('invalidMileage')
            return
          }
          response = await reminderApi.complete(reminder.id, { next_due_mileage: value }, mutationOptions(reminder))
        }
      }
      setReminder(response.data.reminder)
    } catch (err) {
      if ([403, 404, 410].includes(err.response?.status)) {
        setReminder(null)
        setError('unavailable')
      } else if (err.response?.data?.code === 'VEHICLE_ARCHIVED') {
        setError('archived')
      } else {
        setError('actionFailed')
      }
    } finally { setBusy(false) }
  }

  return <main className="p-4 space-y-4 max-w-2xl mx-auto">
    <Link to="/reminders" className="text-sm text-(--color-accent)">{t('reminderDetail.allReminders')}</Link>
    {loading ? <p role="status">{t('common.loading')}</p> : <>
      {error && <div role="alert" className="card space-y-3">
        <p>{t(`reminderDetail.${error}`)}</p>
        {error !== 'unavailable' && <button className="btn btn-secondary" onClick={() => setAttempt(value => value + 1)}>{t('reminderDetail.reload')}</button>}
      </div>}
      {reminder && <article className="card space-y-4" aria-labelledby="reminder-title">
        <h1 id="reminder-title" ref={heading} tabIndex={-1} className="text-xl font-semibold break-words">{reminder.title}</h1>
        {reminder.vehicle_id
          ? <Link className="text-(--color-accent)" to={`/vehicles/${reminder.vehicle_id}`}>{reminder.vehicle_name}</Link>
          : <p>{t('reminders.noVehicle')}</p>}
        {reminder.reminder_type === 'workshop_preparation' && <Link className="btn btn-primary" to={`/vehicles/${reminder.vehicle_id}/appointments`}>{t('appointments.heading')}</Link>}
        <p role="status">{t(`reminderDetail.${reminder.completed ? 'completed' : reminder.dismissed ? 'dismissed' : 'pending'}`)}</p>
        {reminder.description && <p className="whitespace-pre-wrap break-words">{reminder.description}</p>}
        <dl className="space-y-2">
          <div><dt className="text-sm text-(--color-text-muted)">{t('reminderDetail.dueDate')}</dt><dd>{reminder.due_date}</dd></div>
          {reminder.due_mileage != null && <div><dt className="text-sm text-(--color-text-muted)">{t('reminderDetail.dueMileage')}</dt><dd>{reminder.due_mileage.toLocaleString()} {reminder.vehicle_distance_unit || 'km'}</dd></div>}
          {reminder.snoozed_until && <div><dt className="text-sm text-(--color-text-muted)">{t(reminder.reminder_type === 'workshop_preparation' ? 'appointments.preparationAt' : 'reminderDetail.snoozedUntil')}</dt><dd>{new Date(/[zZ]|[+-]\d\d:\d\d$/.test(reminder.snoozed_until) ? reminder.snoozed_until : `${reminder.snoozed_until}Z`).toLocaleString()}</dd></div>}
        </dl>
        {!reminder.completed && !reminder.dismissed && <div className="flex flex-wrap gap-2">
          <button disabled={busy} className="btn btn-primary" onClick={() => act('complete')}>{t('reminders.markComplete')}</button>
          <button disabled={busy} className="btn btn-secondary" onClick={() => act('snooze')}>{t('reminders.snooze7Days')}</button>
          {reminder.vehicle_id && reminder.reminder_type !== 'workshop_preparation' && <Link className="btn btn-secondary" to={`/vehicles/${reminder.vehicle_id}/reminder/add?edit=${reminder.id}`}>{t('reminderDetail.edit')}</Link>}
        </div>}
      </article>}
    </>}
  </main>
}
