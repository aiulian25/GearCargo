import FinancialBasis from '../ui/FinancialBasis'
import { useTranslation } from '../../contexts/LanguageContext'

const CATEGORIES = ['fuel', 'service', 'repair', 'tax', 'parking', 'consumable', 'insurance']

export function ReportSharePrivacyNotice() {
  const { t } = useTranslation()
  return (
    <div className="text-xs text-(--color-text-secondary) space-y-1">
      <p>{t('reportShare.disclosure')}</p>
      <p>{t('reportShare.excluded')}</p>
      <p>{t('reportShare.freeText')}</p>
      <p>{t('reportShare.downloadWarning')}</p>
    </div>
  )
}

export default function ReportSharePreview({ preview }) {
  const { t } = useTranslation()
  return (
    <section aria-label={t('reportShare.previewTitle')} className="rounded-lg bg-(--color-bg-tertiary) p-3 space-y-3">
      <h3 className="text-sm font-medium">{t('reportShare.previewTitle')}</h3>
      <ReportSharePrivacyNotice />
      {preview && <FinancialBasis data={preview} />}
      {!preview ? <p className="text-xs text-(--color-text-muted)">{t('reportShare.previewRequired')}</p> : (
        <div className="space-y-2 text-sm">
          <p>{preview.period_label} · {preview.start_date} - {preview.end_date}</p>
          <ul className="space-y-1">
            {preview.vehicles?.map((vehicle, index) => (
              <li key={index}>{vehicle.name} · {[vehicle.make, vehicle.model].filter(Boolean).join(' ')}</li>
            ))}
          </ul>
          <dl className="space-y-1">
            {CATEGORIES.map(category => (
              <div key={category} className="flex justify-between gap-3">
                <dt>{t(['insurance', 'consumable'].includes(category) ? `financial.${category}` : `charts.${category}`)} ({preview.entry_counts?.[category] || 0})</dt>
                <dd>{Number(preview.totals?.[category] || 0).toFixed(2)} {preview.currency}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-3 font-medium">
              <dt>{t('sharedReport.total')}</dt>
              <dd>{Number(preview.totals?.grand_total || 0).toFixed(2)} {preview.currency}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}
