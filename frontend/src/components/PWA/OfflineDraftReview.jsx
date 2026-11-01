import { useEffect, useState } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

const fieldLabel = name => name.replaceAll('_', ' ').replace(/^./, value => value.toUpperCase())
const textValue = value => value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)

// Ordinary JSON form fields retain their types. Nested form sections are
// editable; arrays use one JSON value per field rather than silently flattening.
function DraftFields({ value, onChange, prefix = '' }) {
  return Object.entries(value).map(([key, item]) => {
    const label = `${prefix}${fieldLabel(key)}`
    const set = next => onChange({ ...value, [key]: next })
    if (item && typeof item === 'object' && !Array.isArray(item)) return <fieldset key={key} className="border p-2 space-y-2"><legend>{label}</legend><DraftFields value={item} onChange={set} /></fieldset>
    if (Array.isArray(item)) return <div key={key}><p>{label}</p>{item.map((entry, index) => <DraftFields key={index} value={{ [index + 1]: entry }} prefix={`${label} `} onChange={next => set(item.map((old, at) => at === index ? next[index + 1] : old))} />)}</div>
    return <label key={key} className="block text-sm">{label}
      {typeof item === 'boolean' ? <input className="ml-2" type="checkbox" checked={item} onChange={event => set(event.target.checked)} />
        : <input className="block w-full rounded border bg-white dark:bg-gray-800 p-2" type={typeof item === 'number' ? 'number' : 'text'} step="any"
          value={item ?? ''} onChange={event => set(typeof item === 'number' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value)} />}
    </label>
  })
}

export default function OfflineDraftReview({ reviewPaused, onChanged }) {
  const { t } = useTranslation()
  const tr = key => t(`pwa.sync.recovery.${key}`)
  const [entries, setEntries] = useState([])
  const [selected, setSelected] = useState(null)
  const [draft, setDraft] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [discard, setDiscard] = useState(null)
  useEffect(() => {
    let current = true
    reviewPaused('list').then(result => { if (current) setEntries(result.entries) }).catch(failure => { if (current) setError(failure.message) })
    return () => { current = false }
  }, [reviewPaused])
  const run = async (type, row) => {
    setBusy(true); setError('')
    try {
      await reviewPaused({ type, id: row.id, version: row.version, body: draft, currentRevision: row.current?.revision })
      setEntries((await reviewPaused('list')).entries)
      setSelected(null); setDiscard(null)
      onChanged?.()
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  const select = row => {
    setSelected(row)
    try { setDraft(JSON.parse(row.body) || {}) } catch { setDraft({}) }
  }
  return <div className="space-y-3">
    <p>{tr('localOnly')}</p>
    {entries.map(row => <article key={row.id} className="border rounded p-3 space-y-2">
      <p className="font-medium">{row.method === 'POST' ? tr('create') : row.method === 'DELETE' ? tr('delete') : tr('edit')} · {row.path.replace('/api/', '')}</p>
      <p>{new Date(row.timestamp).toLocaleString()}</p>
      <p>{tr(row.reason)}</p>
      {row.error?.httpStatus && <p>{tr('serverStatus')}: {row.error.httpStatus}</p>}
      <button type="button" disabled={busy} className="underline" onClick={() => select(row)}>{tr('reviewDraft')}</button>
      {selected?.id === row.id && <div className="space-y-3">
        {row.reason === 'mutation_conflict' && <>
          <p>{tr('compare')}</p>
          <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>{tr('field')}</th><th>{tr('yourDraft')}</th><th>{tr('savedRecord')}</th></tr></thead>
            <tbody>{Object.entries(draft).map(([key, value]) => <tr key={key}><th>{fieldLabel(key)}</th><td className="p-2 break-all">{textValue(value)}</td><td className="p-2 break-all">{textValue(row.current?.[key])}</td></tr>)}</tbody></table></div>
        </>}
        {row.recoverable && ['validation_failed', 'mutation_conflict'].includes(row.reason)
          && (row.reason !== 'mutation_conflict' || (row.error?.code === 'REVISION_CONFLICT' && row.current?.revision)) ? <>
            {row.method !== 'DELETE' && <DraftFields value={draft} onChange={setDraft} />}
            <button type="button" disabled={busy || !navigator.onLine} className="rounded bg-blue-600 text-white p-2" onClick={() => run('repair', row)}>{tr('apply')}</button>
          </> : <pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(draft, null, 2)}</pre>}
        {row.recoverable && ['sign_in_required', 'identity_changed', 'retention_expired'].includes(row.reason) && <button type="button" disabled={busy || !navigator.onLine} className="rounded bg-blue-600 text-white p-2" onClick={() => run('resume', row)}>{tr('resume')}</button>}
        <button type="button" disabled={busy} className="ml-3 underline" onClick={() => setDiscard(row.id)}>{tr('discard')}</button>
        {discard === row.id && <div role="alert"><p>{t('pwa.sync.discardConfirm')}</p><button type="button" disabled={busy} onClick={() => run('discard', row)}>{t('common.confirm')}</button><button type="button" onClick={() => setDiscard(null)} className="ml-3">{t('common.cancel')}</button></div>}
      </div>}
    </article>)}
    {error && <p role="alert">{error}</p>}
  </div>
}
