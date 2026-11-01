import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { reconciliationApi, vehicleApi } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { useUnsavedChanges } from '../hooks/useUnsavedChanges';
import { useTranslation } from '../contexts/LanguageContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import AttachmentViewer from '../components/ui/AttachmentViewer';
import { mutationOptions } from '../utils/mutationProtocol';
import { privateNavigationState } from '../utils/privateNavigation';
import { parseStatementCsv, normalizeStatement, statementFingerprint, cents, money } from '../utils/statementCsv';
function ImportStatement({ onCreated }) {
  const { t } = useTranslation();
  const tr = key => t(`reconciliation.${key}`);
  const [text, setText] = useState('');
  const [sourceKey, setSourceKey] = useState('');
  const [settings, setSettings] = useState({
    delimiter: ',',
    decimal: '.',
    dateFormat: 'iso',
    sign: 'expense'
  });
  const [mapping, setMapping] = useState({
    date: '',
    amount: '',
    currency: '',
    vendor: ''
  });
  const [selected, setSelected] = useState(new Set());
  const [name, setName] = useState('');
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const intent = useRef(null);
  const fileGeneration = useRef(0);
  const markSaved = useUnsavedChanges(Boolean(text));
  let parsed, parseError;
  try {
    if (text) parsed = parseStatementCsv(text, settings.delimiter);
  } catch (e) {
    parseError = e.message;
  }
  const reset = () => {
    setPreview(null);
    intent.current = null;
    setError('');
  };
  const file = async event => {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    const generation = ++fileGeneration.current;
    reset();
    setText('');
    setSelected(new Set());
    setPage(0);
    try {
      if (chosen.size > 2 * 1024 * 1024) throw new Error('fileLimit');
      const bytes = await chosen.arrayBuffer();
      const fingerprint = await statementFingerprint(bytes);
      if (generation !== fileGeneration.current) return;
      setSourceKey(fingerprint);
      setText(new TextDecoder('utf-8', {
        fatal: true
      }).decode(bytes));
    } catch (e) {
      setError(tr(e.message === 'fileLimit' ? e.message : 'invalid'));
    }
  };
  const prepare = () => {
    try {
      if (!name.trim() || name.trim().length > 100) throw new Error('name');
      setPreview({
        name: name.trim(),
        source_key: sourceKey,
        rows: normalizeStatement(parsed, selected, mapping, settings)
      });
      setError('');
    } catch (e) {
      setError(tr(e.message));
    }
  };
  const upload = async () => {
    setBusy(true);
    setError('');
    try {
      if (!navigator.onLine) throw new Error('online');
      const checked = (await reconciliationApi.preview(preview)).data;
      if (checked.conflict) throw new Error('selectionChanged');
      intent.current ||= mutationOptions();
      const saved = await reconciliationApi.create(preview, intent.current);
      if (markSaved()) onCreated(saved.data.id);
    } catch (e) {
      setError(e.response?.data?.message_key ? t(e.response.data.message_key) : tr(e.message === 'selectionChanged' || e.message === 'online' ? e.message : 'failed'));
    } finally {
      setBusy(false);
    }
  };
  return <section className="card p-4 space-y-4">
    <h2 className="text-lg font-semibold">{tr('import')}</h2><p>{tr('privacy')}</p>
    <label className="block">{tr('file')}<input aria-label={tr('file')} type="file" accept=".csv,text/csv" onChange={file} disabled={busy} className="block mt-2" /></label>
    <div className="grid gap-3 sm:grid-cols-2">
      <label>{tr('name')}<input className="input w-full" value={name} maxLength={100} disabled={busy} onChange={e => {
          setName(e.target.value);
          reset();
        }} /></label>
      {Object.entries({
        delimiter: [[',', 'comma'], [';', 'semicolon'], ['\t', 'tab']],
        decimal: [['.', 'dot'], [',', 'comma']],
        dateFormat: [['iso', 'iso'], ['dmy', 'dmy'], ['mdy', 'mdy']],
        sign: [['expense', 'expensePositive'], ['bank', 'bankNegative']]
      }).map(([key, options]) => <label key={key}>{tr(key)}<select aria-label={tr(key)} className="input w-full" value={settings[key]} disabled={busy} onChange={e => {
          setSettings({
            ...settings,
            [key]: e.target.value
          });
          reset();
          if (key === 'delimiter') {
            setSelected(new Set());
            setMapping({
              date: '',
              amount: '',
              currency: '',
              vendor: ''
            });
          }
        }}>{options.map(([value, label]) => <option key={value} value={value}>{tr(label)}</option>)}</select></label>)}
    </div>
    {parseError && <p role="alert">{tr(parseError)}</p>}
    {parsed && <>
      <p>{tr('mapHelp')}</p><div className="grid gap-3 sm:grid-cols-4">{Object.keys(mapping).map(key => <label key={key}>{tr(key)}<select aria-label={tr(key)} className="input w-full" value={mapping[key]} disabled={busy} onChange={e => {
            setMapping({
              ...mapping,
              [key]: e.target.value
            });
            reset();
          }}><option value="">{tr('choose')}</option>{parsed.columns.map((column, index) => <option key={index} value={index}>{index + 1}: {column}</option>)}</select></label>)}</div>
      <div className="flex gap-3 flex-wrap"><button className="btn btn-secondary" disabled={busy || parsed.rows.length > 2000} onClick={() => {
          setSelected(new Set(parsed.rows.map(r => r.row_number)));
          reset();
        }}>{tr('selectAll')}</button><button className="btn btn-secondary" disabled={busy} onClick={() => {
          setSelected(new Set());
          reset();
        }}>{tr('selectNone')}</button><span>{tr('selected')}: {selected.size}</span></div>
      <div className="overflow-x-auto max-h-80"><table className="w-full text-sm"><thead><tr><th>{tr('include')}</th>{parsed.columns.map((c, i) => <th key={i} className="p-2 text-left">{c}</th>)}</tr></thead><tbody>{parsed.rows.slice(page * 50, page * 50 + 50).map(row => <tr key={row.row_number}><td><input type="checkbox" aria-label={`${tr('include')} ${row.row_number}`} checked={selected.has(row.row_number)} disabled={busy} onChange={e => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(row.row_number);else next.delete(row.row_number);
                  setSelected(next);
                  reset();
                }} /></td>{row.cells.map((c, i) => <td key={i} className="p-2 max-w-64 break-words">{c}</td>)}</tr>)}</tbody></table></div>
      <div className="flex gap-3"><button className="btn btn-secondary" disabled={!page} onClick={() => setPage(page - 1)}>{tr('previous')}</button><button className="btn btn-secondary" disabled={(page + 1) * 50 >= parsed.rows.length} onClick={() => setPage(page + 1)}>{tr('next')}</button></div>
      <button className="btn btn-primary" disabled={busy || !selected.size} onClick={prepare}>{tr('preview')}</button>
    </>}
    {preview && <div className="space-y-3"><h3 className="font-semibold">{tr('selectedPreview')}</h3><p>{tr('signHelp')}</p><div className="max-h-64 overflow-auto"><table className="w-full"><thead><tr>{['date', 'amount', 'currency', 'vendor'].map(k => <th key={k} className="text-left p-2">{tr(k)}</th>)}</tr></thead><tbody>{preview.rows.map(r => <tr key={r.row_number}>{['date', 'amount', 'currency', 'vendor'].map(k => <td className="p-2" key={k}>{r[k]}</td>)}</tr>)}</tbody></table></div><button className="btn btn-primary" disabled={busy} onClick={upload}>{tr('upload')}</button></div>}
    {error && <p role="alert" className="text-red-500">{error}</p>}
  </section>;
}
function RowReview({
  batch,
  row,
  vehicles,
  onSaved,
  onClose
}) {
  const { t } = useTranslation();
  const tr = key => t(`reconciliation.${key}`);
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [allocations, setAllocations] = useState({});
  const [reason, setReason] = useState(row.exclusion_reason || '');
  const [vehicle, setVehicle] = useState('');
  const [kind, setKind] = useState('service');
  const [attachment, setAttachment] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const intent = useRef(null);
  const markSaved = useUnsavedChanges(Object.keys(allocations).length > 0 || reason !== (row.exclusion_reason || ''));
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    reconciliationApi.candidates(batch.id, row.id, page, search).then(({
      data
    }) => {
      if (alive) {
        setCandidates(data.candidates);
        setMore(data.more);
      }
    }).catch(() => {
      if (alive) setError(t('reconciliation.failed'));
    }).finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [batch.id, row.id, page, search, t]);
  const change = () => {
    intent.current = null;
    setError('');
  };
  const save = async () => {
    setBusy(true);
    setError('');
    try {
      if (!navigator.onLine) throw new Error('online');
      const matches = Object.values(allocations).filter(v => v.amount.trim()).map(v => ({
        entry_id: v.entry.id,
        revision: v.entry.revision,
        amount: money(cents(v.amount))
      }));
      intent.current ||= mutationOptions(batch);
      await reconciliationApi.match(batch.id, row.id, {
        matches,
        exclusion_reason: reason.trim() || null
      }, intent.current);
      if (markSaved()) onSaved();
    } catch (e) {
      setError(e.response?.data?.message_key ? t(e.response.data.message_key) : tr(e.response?.status === 409 ? 'changed' : e.message === 'online' ? 'online' : 'failed'));
    } finally {
      setBusy(false);
    }
  };
  const draft = () => navigate(`/vehicles/${vehicle}/${kind}/add`, {
    state: privateNavigationState({
      prefill: {
        date: row.date,
        amount: row.remaining,
        currency: row.currency,
        vendor: row.vendor
      },
      reconciliationReturnTo: `/reconciliation?batch=${batch.id}`
    })
  });
  let allocated = '—',
    remaining = '—';
  try {
    const total = Object.values(allocations).reduce((s, v) => s + (v.amount.trim() ? cents(v.amount) : 0n), 0n);
    allocated = money(total);
    remaining = money(cents(row.amount) - total);
  } catch {/* field validation on save */}
  return <section className="card p-4 space-y-4" aria-label={tr('review')}>
    <h3 className="text-lg font-semibold">{tr('review')}: {row.date} · {row.vendor} · {row.amount} {row.currency}</h3>
    <p>{tr('replaceHelp')}</p>{row.matches.length > 0 && <ul>{row.matches.map(m => <li key={m.id}>{tr('expenseId')} {m.entry_id ?? '—'}: {m.amount} {row.currency} · {tr(m.valid ? 'matched' : 'needs_review')}</li>)}</ul>}
    <label className="block">{tr('search')}<input className="input w-full" value={search} maxLength={120} onChange={e => {
        setSearch(e.target.value);
        setPage(1);
      }} /></label>
    {loading && <p role="status">{tr('loading')}</p>}
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['expense', 'available', 'amount', 'receipt'].map(k => <th key={k} className="text-left p-2">{tr(k)}</th>)}</tr></thead><tbody>{candidates.map(e => <tr key={e.id}><td className="p-2">{e.date} · {e.title}<br />{vehicles.find(v => v.id === e.vehicle_id)?.name} · {e.vendor}<br />{e.exact ? tr('exact') : ''} {e.vendor_match ? tr('vendorMatch') : ''}</td><td className="p-2">{e.available} {e.currency}</td><td className="p-2"><input className="input w-32" aria-label={`${tr('amount')} ${e.title}`} inputMode="decimal" disabled={busy} value={allocations[e.id]?.amount || ''} onChange={event => {
                setAllocations({
                  ...allocations,
                  [e.id]: {
                    entry: e,
                    amount: event.target.value
                  }
                });
                change();
              }} /></td><td>{e.attachments.map(a => <button key={a.id} className="btn btn-secondary" onClick={() => setAttachment(a)}>{a.original_filename || tr('receipt')}</button>)}</td></tr>)}</tbody></table></div>
    {!loading && !candidates.length && <p>{tr('noCandidates')}</p>}
    <div className="flex gap-3"><button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>{tr('previous')}</button><button className="btn btn-secondary" disabled={!more} onClick={() => setPage(page + 1)}>{tr('next')}</button></div>
    <p>{tr('allocated')}: {allocated} {row.currency} · {tr('remaining')}: {remaining} {row.currency}</p>
    {Object.values(allocations).filter(v => v.amount).map(v => <p key={v.entry.id}>{v.entry.title}: {v.amount} <button className="btn btn-secondary" disabled={busy} onClick={() => {
        const next = {
          ...allocations
        };
        delete next[v.entry.id];
        setAllocations(next);
        change();
      }}>{tr('remove')}</button></p>)}
    <label className="block">{tr('exclusion_reason')}<input className="input w-full" value={reason} maxLength={255} disabled={busy} onChange={e => {
        setReason(e.target.value);
        change();
      }} /></label>
    <div className="flex gap-3"><button className="btn btn-primary" disabled={busy} onClick={save}>{tr('confirmMatches')}</button><button className="btn btn-secondary" disabled={busy} onClick={onClose}>{tr('close')}</button></div>
    <div className="border-t pt-4 space-y-3"><h4 className="font-semibold">{tr('draft')}</h4><p>{tr('draftHelp')}</p><label>{tr('vehicle')}<select aria-label={tr('vehicle')} className="input w-full" value={vehicle} onChange={e => setVehicle(e.target.value)}><option value="">{tr('choose')}</option>{vehicles.filter(v => !v.archived).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label><label>{tr('type')}<select aria-label={tr('type')} className="input w-full" value={kind} onChange={e => setKind(e.target.value)}>{['fuel', 'service', 'repair', 'tax', 'parking', 'consumable'].map(k => <option key={k} value={k}>{tr(k)}</option>)}</select></label><button className="btn btn-secondary" disabled={!vehicle || busy || row.remaining === '0.00'} onClick={draft}>{tr('openDraft')}</button></div>
    {error && <p role="alert" className="text-red-500">{error}</p>}
    {attachment && <AttachmentViewer attachment={attachment} isOpen onClose={() => setAttachment(null)} />}
  </section>;
}
function ReconciliationPage() {
  const { t } = useTranslation();
  const tr = key => t(`reconciliation.${key}`);
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const batchId = params.get('batch');
  const [batches, setBatches] = useState([]);
  const [batch, setBatch] = useState(null);
  const [row, setRow] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [listPage, setListPage] = useState(1);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const intents = useRef(new Map());
  const loaded = useCallback(() => {
    setRow(null);
    setReload(v => v + 1);
  }, []);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    setBatch(null);
    setRow(null);
    Promise.all([reconciliationApi.list(listPage), vehicleApi.getAll(), batchId ? reconciliationApi.get(batchId) : Promise.resolve(null)]).then(([list, cars, record]) => {
      if (alive) {
        setBatches(list.data.batches);
        setMore(list.data.more);
        setVehicles(cars.data.vehicles || cars.data);
        setBatch(record?.data || null);
      }
    }).catch(() => {
      if (alive) setError(t('reconciliation.failed'));
    }).finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [batchId, listPage, reload, t]);
  const action = async type => {
    if (type === 'delete' && !(await confirm({
      title: tr('delete'),
      message: tr('deleteHelp'),
      confirmLabel: tr('delete'),
      destructive: true
    }))) return;
    setBusy(true);
    setError('');
    try {
      if (!navigator.onLine) throw new Error('online');
      const key = `${type}:${batch.id}:${batch.revision}`;
      if (!intents.current.has(key)) intents.current.set(key, mutationOptions(batch));
      if (type === 'delete') {
        await reconciliationApi.delete(batch.id, intents.current.get(key));
        setParams({});
        loaded();
      } else {
        await reconciliationApi.complete(batch.id, intents.current.get(key));
        loaded();
      }
    } catch (e) {
      setError(e.response?.data?.message_key ? t(e.response.data.message_key) : tr(e.response?.status === 409 ? 'changed' : e.message === 'online' ? 'online' : 'failed'));
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    try {
      const result = await reconciliationApi.summary(batch.id);
      const url = URL.createObjectURL(result.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `statement-${batch.id}-summary.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError(tr('failed'));
    }
  };
  return <div className="max-w-6xl mx-auto p-4 space-y-5"><Link className="text-primary-500" to="/settings">{tr('settings')}</Link><h1 className="text-2xl font-bold">{tr('title')}</h1><p>{tr('intro')}</p>
    {error && <div role="alert" className="text-red-500">{error} <button className="btn btn-secondary" onClick={loaded}>{tr('reload')}</button></div>}
    {loading ? <p role="status">{tr('loading')}</p> : batch ? <>
      <section className="card p-4 space-y-3"><h2 className="text-xl font-semibold">{batch.name} · {tr(batch.effective_status)}</h2><p>{tr('totalsHelp')}</p>{Object.entries(batch.totals).map(([currency, totals]) => <p key={currency}><strong>{currency}</strong> · {['statement', 'allocated', 'excluded', 'remaining'].map(k => `${tr(k)}: ${totals[k]}`).join(' · ')}</p>)}<div className="flex flex-wrap gap-3"><button className="btn btn-primary" disabled={busy || !batch.resolved || !!row} onClick={() => action('complete')}>{tr('complete')}</button><button className="btn btn-secondary" onClick={download}>{tr('export')}</button><button className="btn btn-secondary" disabled={busy} onClick={() => action('delete')}>{tr('delete')}</button><button className="btn btn-secondary" onClick={() => setParams({})}>{tr('back')}</button></div></section>
      <div className="card overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['date', 'vendor', 'amount', 'allocated', 'remaining', 'status', 'review'].map(k => <th className="text-left p-3" key={k}>{tr(k)}</th>)}</tr></thead><tbody>{batch.transactions.map(r => <tr key={r.id}><td className="p-3">{r.date}</td><td className="p-3">{r.vendor}</td><td className="p-3">{r.amount} {r.currency}</td><td className="p-3">{r.allocated}</td><td className="p-3">{r.remaining}</td><td className="p-3">{tr(r.status)}{r.exclusion_reason && <p>{r.exclusion_reason}</p>}</td><td className="p-3"><button className="btn btn-secondary" disabled={busy} onClick={() => setRow(r)}>{tr('review')}</button></td></tr>)}</tbody></table></div>
      {row && <RowReview key={`${batch.id}:${row.id}:${batch.revision}`} batch={batch} row={row} vehicles={vehicles} onSaved={loaded} onClose={() => setRow(null)} />}
    </> : <><ImportStatement onCreated={id => {
        setParams({
          batch: String(id)
        });
        loaded();
      }} /><section className="card p-4 space-y-3"><h2 className="text-lg font-semibold">{tr('batches')}</h2>{batches.length ? batches.map(b => <div key={b.id}><button className="btn btn-secondary" onClick={() => setParams({
            batch: String(b.id)
          })}>{b.name}</button></div>) : <p>{tr('empty')}</p>}<div className="flex gap-3"><button className="btn btn-secondary" disabled={listPage === 1} onClick={() => setListPage(listPage - 1)}>{tr('previous')}</button><button className="btn btn-secondary" disabled={!more} onClick={() => setListPage(listPage + 1)}>{tr('next')}</button></div></section></>}
  </div>;
}
export default function Reconciliation() {
  const { user } = useAuth();
  return <ReconciliationPage key={user?.id || 'signed-out'} />;
}
