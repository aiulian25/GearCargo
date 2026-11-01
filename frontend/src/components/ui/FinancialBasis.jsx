import { useDateFormat } from '../../hooks/useDateFormat'
import { useTranslation } from '../../contexts/LanguageContext'

export default function FinancialBasis({ data, error = false }) {
  const { t } = useTranslation()
  const { formatDate } = useDateFormat()
  return <div className="text-xs text-(--color-text-secondary) my-3 space-y-1" role="status">
    <p>{t(error ? 'financial.loadFailed' : data ? 'financial.basis' : 'common.loading')}</p>
    {data?.display_currency && <p>{t('settings.currency')}: {data.display_currency}</p>}
    {(data?.end_date || data?.as_of) && <p>{t('financial.asOf')} {formatDate(data.end_date || data.as_of)}</p>}
    {data?.converted === false && <p>{t('financial.partial')}</p>}
    {data?.fx_applied && <p>{t('financial.currentRates')}</p>}
  </div>
}
