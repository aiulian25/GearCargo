import { useEffect, useRef } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

export default function ImportReview({ preview, busy, onApply, onCancel }) {
  const { t } = useTranslation()
  const heading = useRef(null)
  useEffect(() => { if (preview) heading.current?.focus() }, [preview])
  if (!preview) return null
  return (
    <section className="card p-4 space-y-3 border-2 border-(--color-primary)" aria-labelledby="import-review-title">
      <h3 id="import-review-title" ref={heading} tabIndex={-1} className="font-semibold">{t('backup.importReview.title')}</h3>
      <p className="text-sm">{t('backup.importReview.explanation')}</p>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        {['new_records', 'exact_repeats', 'possible_duplicates', 'conflicts', 'error_count'].map(key => (
          <div key={key}><dt>{t(`backup.recordTypes.${key}`)}</dt><dd>{preview[key] || 0}</dd></div>
        ))}
      </dl>
      {preview.conflicts > 0 && <p className="text-sm">{t('backup.importReview.keepHint')}</p>}
      {preview.blocked && <p role="alert" className="text-sm text-red-500">{t(preview.statement_collision ? 'reconciliation.sourceCollision' : 'backup.importReview.unitsBlocked')}</p>}
      <ul className="text-sm space-y-2 max-h-64 overflow-auto">
        {(preview.records || []).filter(row => row.reason || row.possible_duplicate_ids?.length).map(row => (
          <li key={`${row.kind}-${row.archive_id}`}>
            {t(`backup.recordTypes.${row.kind}`)} · {row.source_id}: {' '}
            {t(row.reason === 'statement_source_collision' ? 'reconciliation.sourceCollision' : `backup.importReview.${row.reason || 'possible'}`)}
            {row.existing_id != null && ` (#${row.existing_id})`}
          </li>
        ))}
        {(preview.errors || []).map(issue => <li key={`error-${issue.row}`}>
          {t('backup.importReview.row')} {issue.row}: {issue.error}
        </li>)}
      </ul>
      {preview.records_truncated && <p className="text-xs">{t('backup.importReview.truncated')}</p>}
      <div className="flex gap-2 flex-wrap">
        <button type="button" className="btn btn-primary" disabled={busy || preview.blocked} onClick={onApply}>
          {t(busy ? 'backup.importing' : preview.conflicts ? 'backup.importReview.keepApply' : 'backup.importReview.apply')}
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>{t('common.cancel')}</button>
      </div>
    </section>
  )
}
