import { useTranslation } from '../../contexts/LanguageContext'

export default function ExpensePagination({ data, page, onPage, loading = false }) {
  const { t } = useTranslation()
  if (!data) return null
  return <nav aria-label={t('expensePages.pagination')} className="flex flex-wrap items-center justify-between gap-3 py-3">
    <span className="text-sm">{t('expensePages.page').replace('{page}', String(page)).replace('{pages}', String(Math.max(1, data.pages))).replace('{total}', String(data.total))}</span>
    <div className="flex gap-2">
      <button className="btn btn-secondary btn-sm" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>{t('expensePages.previous')}</button>
      <button className="btn btn-secondary btn-sm" disabled={loading || page >= data.pages} onClick={() => onPage(page + 1)}>{t('expensePages.next')}</button>
    </div>
  </nav>
}
