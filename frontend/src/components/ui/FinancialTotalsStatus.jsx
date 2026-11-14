import { useTranslation } from '../../contexts/LanguageContext'

function statusMessageKey(data, error) {
  if (error) return 'financial.loadFailed'
  if (!data) return 'common.loading'
  if (data.converted === false) return 'financial.partial'
  return null
}

/** Says something only when totals are loading, failed to load, or leave amounts out. */
export default function FinancialTotalsStatus({ data, error = false }) {
  const { t } = useTranslation()
  const messageKey = statusMessageKey(data, error)
  if (!messageKey) return null
  return <p className="text-xs text-(--color-text-secondary) my-3" role="status">{t(messageKey)}</p>
}
