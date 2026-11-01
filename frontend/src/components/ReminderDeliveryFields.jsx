import { useId } from 'react'
import { useTranslation } from '../contexts/LanguageContext'

export default function ReminderDeliveryFields({ register, errors }) {
  const { t } = useTranslation()
  const id = useId()
  return <fieldset className="card space-y-3">
    <legend className="text-sm font-medium">{t('reminderDelivery.title')}</legend>
    <label className="block text-sm" htmlFor={`${id}-lead`}>{t('reminderDelivery.leadDays')}</label>
    <input id={`${id}-lead`} type="number" min="0" step="1" className="input"
      {...register('notify_days_before', { required: true, min: 0, valueAsNumber: true })} />
    {errors.notify_days_before && <p role="alert" className="text-sm text-red-500">{t('validation.invalidNumber')}</p>}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('notify_push')} />{t('reminderDelivery.push')}</label>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register('notify_email')} />{t('reminderDelivery.email')}</label>
    <p className="text-xs text-(--color-text-muted)">{t('reminderDelivery.timing')}</p>
  </fieldset>
}
