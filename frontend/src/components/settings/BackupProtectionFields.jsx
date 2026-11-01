import { useId } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

export default function BackupProtectionFields({ title, enabled, onEnabled, passphrase, onPassphrase,
  confirmation, onConfirmation, stored = false }) {
  const { t } = useTranslation()
  const id = useId()
  return <fieldset className="space-y-3 rounded-xl border border-(--color-border) p-4">
    <legend className="px-1 text-sm font-medium">{title}</legend>
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={enabled} onChange={event => onEnabled(event.target.checked)} />
      {t('backup.protection.encrypt')}
    </label>
    {enabled ? <>
      <p className="text-xs text-(--color-text-secondary)">{t('backup.protection.recovery')}</p>
      {stored && <p className="text-xs">{t('backup.protection.savedKey')}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label htmlFor={`${id}-key`} className="text-sm">{t('backup.protection.passphrase')}
          <input id={`${id}-key`} type="password" autoComplete="new-password" className="input mt-1 w-full"
            maxLength={1024} value={passphrase} onChange={event => onPassphrase(event.target.value)} />
        </label>
        <label htmlFor={`${id}-confirm`} className="text-sm">{t('backup.protection.confirm')}
          <input id={`${id}-confirm`} type="password" autoComplete="new-password" className="input mt-1 w-full"
            maxLength={1024} value={confirmation} onChange={event => onConfirmation(event.target.value)} />
        </label>
      </div>
    </> : <p className="text-sm text-amber-700 dark:text-amber-400">{t('backup.protection.plainWarning')}</p>}
  </fieldset>
}
