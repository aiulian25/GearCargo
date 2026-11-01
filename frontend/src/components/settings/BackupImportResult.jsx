import { useTranslation } from '../../contexts/LanguageContext'

// Keep the result on screen: a warning toast followed by reload hides recovery gaps.
export default function BackupImportResult({ result, onRefresh }) {
  const { t } = useTranslation()
  if (!result) return null
  const warnings = result.warnings || []
  const counts = Object.entries(result).filter(([key, value]) => typeof value === 'number' && value > 0 && !['created', 'skipped', 'total', 'skipped_duplicates'].includes(key))
  return (
    <section className="card p-4 space-y-3" aria-labelledby="backup-import-result" role="status">
      <h3 id="backup-import-result" className="font-semibold">
        {t(warnings.length ? 'backup.resultReview' : 'backup.importSuccess')}
      </h3>
      {result.source_version && <p className="text-sm text-(--color-text-secondary)">
        {t('backup.resultVersion', { version: result.source_version })}
      </p>}
      <dl className="grid grid-cols-2 gap-2 text-sm">
        {counts.map(([key, count]) => (
          <div key={key}>
            <dt>{t(`backup.recordTypes.${key}`)}</dt>
            <dd>{count}</dd>
          </div>
        ))}
      </dl>
      {result.errors?.length > 0 && <ul className="list-disc pl-5 text-sm">
        {result.errors.map(issue => <li key={issue.row}>{t('backup.importReview.row')} {issue.row}: {issue.error}</li>)}
      </ul>}
      {warnings.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{t('backup.resultWarnings', { count: warnings.length })}</p>
          <ul className="list-disc pl-5 space-y-1 text-sm max-h-64 overflow-auto">
            {warnings.map((warning, index) => (
              <li key={`${warning.code}-${warning.path}-${index}`}>
                {t(`backup.warningTypes.${warning.code}`)}
                {warning.path && <span className="text-(--color-text-muted)"> ({warning.path})</span>}
                {warning.code === 'missing_fields' && <p className="text-xs">{warning.message}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <button type="button" className="btn btn-primary" onClick={onRefresh}>
        {t('backup.resultRefresh')}
      </button>
    </section>
  )
}
