import { useEffect, useState } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

export default function ReceiptDraftReview({ count, version, reviewReceipts, triggerSync }) {
  const { t } = useTranslation()
  const tr = key => t(`pwa.sync.receipts.${key}`)
  const [entries, setEntries] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)
  useEffect(() => {
    let active = true
    if (count) reviewReceipts({ type: 'list' }).then(result => { if (active) setEntries(result.entries) }).catch(failure => { if (active) setError(failure.message) })
    else setEntries([])
    return () => { active = false }
  }, [count, version, reviewReceipts])
  const act = async (type, row) => {
    setBusy(true); setError('')
    try {
      const result = await reviewReceipts({ type, id: row.id, version: row.version })
      if (type === 'download') {
        const url = URL.createObjectURL(result.blob)
        const link = document.createElement('a')
        link.href = url; link.download = result.name; link.click()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
      if (type === 'retry') await triggerSync()
      setConfirm(null)
      setEntries((await reviewReceipts({ type: 'list' })).entries)
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  if (!count) return null
  return <section className="my-3 rounded-lg border border-amber-400 p-3 text-sm space-y-3" aria-label={tr('title')}>
    <h4 className="font-medium">{tr('title')} ({count})</h4>
    <p>{tr('notice')}</p>
    {entries.map(row => <article key={row.id} className="border-t pt-2 space-y-2">
      <p className="font-medium break-all">{row.name}</p>
      <p>{row.resource} · {tr(row.parentId ? 'parentSaved' : 'waiting_parent')}</p>
      <p>{tr(row.status)}</p>
      {row.error?.httpStatus && <p>{tr('serverStatus')}: {row.error.httpStatus}</p>}
      {row.status === 'mutation_conflict' && row.current && <p>{tr('currentLink')}: {row.current.entry_id ?? tr('unlinked')} · {row.current.description || row.current.category}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={busy || !navigator.onLine || !row.parentId || ['parent_conflict', 'parent_missing'].includes(row.status)} onClick={() => act('retry', row)}>{tr('retry')}</button>
        {row.hasFile && <button type="button" disabled={busy} onClick={() => act('download', row)}>{tr('download')}</button>}
        {row.attachmentId && <a href={`/vehicles/${row.vehicleId}/documents?open=${row.attachmentId}`}>{tr('uploadedFile')}</a>}
        <button type="button" disabled={busy} onClick={() => setConfirm(row.id)}>{tr('remove')}</button>
      </div>
      {confirm === row.id && <div role="alert"><p>{tr('removeConfirm')}</p><button type="button" disabled={busy} onClick={() => act('remove', row)}>{t('common.confirm')}</button><button type="button" className="ml-3" onClick={() => setConfirm(null)}>{t('common.cancel')}</button></div>}
    </article>)}
    {error && <p role="alert">{error}</p>}
  </section>
}
