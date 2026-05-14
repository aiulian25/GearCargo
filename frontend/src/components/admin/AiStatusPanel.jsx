import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { predictionApi, adminApi } from '../../services/api'
const Icons = {
  cpu: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
    </svg>
  ),
  refresh: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  chevronDown: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  ),
  chevronUp: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
    </svg>
  ),
  check: (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
    </svg>
  ),
  info: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
}

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return null
  const k = 1024 * 1024 * 1024 // GB
  if (bytes >= k) return (bytes / k).toFixed(1) + ' GB'
  const m = 1024 * 1024
  if (bytes >= m) return (bytes / m).toFixed(0) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

const formatRelativeTime = (isoString) => {
  if (!isoString) return null
  const diff = Date.now() - new Date(isoString).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

const StatusBadge = ({ status }) => {
  const config = {
    online:   { bg: 'bg-green-500/10',  text: 'text-green-600 dark:text-green-400',  dot: 'bg-green-500',  label: 'Online'    },
    offline:  { bg: 'bg-red-500/10',    text: 'text-red-600 dark:text-red-400',      dot: 'bg-red-500',    label: 'Offline'   },
    error:    { bg: 'bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400',dot: 'bg-yellow-500', label: 'Error'     },
    disabled: { bg: 'bg-gray-500/10',   text: 'text-gray-500',                        dot: 'bg-gray-400',   label: 'Disabled'  },
    loading:  { bg: 'bg-blue-500/10',   text: 'text-blue-500',                        dot: 'bg-blue-400',   label: 'Checking…' },
  }
  const c = config[status] || config.disabled
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} ${status === 'loading' ? 'animate-pulse' : ''}`} />
      {c.label}
    </span>
  )
}

export default function AiStatusPanel() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [showModels, setShowModels] = useState(false)
  // Per-task model assignment state
  const [taskModels, setTaskModels] = useState({ global: '', predict: '', ocr: '', anomaly: '', reminder: '' })
  const [savingModels, setSavingModels] = useState(false)
  const [modelSaveMsg, setModelSaveMsg] = useState(null)  // { ok: bool, text: string }
  // AI cache flush state
  const [flushingCache, setFlushingCache] = useState(false)
  const [flushMsg, setFlushMsg] = useState(null)          // { ok: bool, text: string }

  const loadSettings = useCallback(async () => {
    setLoading(true)
    try {
      const res = await adminApi.getSettings()
      setSettings(res.data)
      // Pre-populate task model selectors from API response
      const tm = res.data?.task_models || {}
      setTaskModels({
        global:   tm.global   || '',
        predict:  tm.predict  || '',
        ocr:      tm.ocr      || '',
        anomaly:  tm.anomaly  || '',
        reminder: tm.reminder || '',
      })
    } catch (err) {
      console.error('Failed to load AI settings', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await predictionApi.getStatus()
      setTestResult(res.data)
    } catch (err) {
      setTestResult({ status: 'error', message: err.response?.data?.error || 'Request failed' })
    } finally {
      setTesting(false)
    }
  }

  const handleSaveModels = async () => {
    setSavingModels(true)
    setModelSaveMsg(null)
    try {
      await adminApi.updateSettings({ task_models: taskModels })
      setModelSaveMsg({ ok: true, text: t('aiPredictions.modelsSaved') || 'Model settings saved' })
    } catch (err) {
      setModelSaveMsg({ ok: false, text: t('aiPredictions.modelsSaveError') || 'Failed to save model settings' })
    } finally {
      setSavingModels(false)
    }
  }

  const handleFlushCache = async () => {
    if (!window.confirm(t('aiPredictions.flushCacheConfirm') || 'Clear all cached AI responses? The next request for each feature will call Ollama fresh.')) return
    setFlushingCache(true)
    setFlushMsg(null)
    try {
      const res = await adminApi.flushAiCache()
      const deleted = res.data?.deleted ?? 0
      setFlushMsg({ ok: true, text: (t('aiPredictions.flushCacheSuccess') || `Cleared {n} cached AI response(s).`).replace('{n}', deleted) })
      // Reload settings to update the key count
      await loadSettings()
    } catch {
      setFlushMsg({ ok: false, text: t('aiPredictions.flushCacheError') || 'Failed to flush AI cache.' })
    } finally {
      setFlushingCache(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    )
  }

  if (!settings) {
    return (
      <p className="text-sm text-[var(--color-text-muted)] text-center py-4">
        {t('common.loadFailed') || 'Failed to load settings'}
      </p>
    )
  }

  const live = settings.ollama_live || {}
  const stats = settings.prediction_stats || {}
  const displayStatus = live.status || (settings.ollama_enabled ? 'offline' : 'disabled')
  const models = live.models || []
  const activeResult = testResult || live

  return (
    <div className="space-y-4">

      {/* ── Ollama downtime warning banner (>1 h offline) ── */}
      {settings?.ollama_downtime?.down && settings.ollama_downtime.duration_min >= 60 && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/25">
          <svg className="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
          <div className="min-w-0 space-y-0.5">
            <p className="text-xs font-medium text-red-600 dark:text-red-400">
              {(t('aiPredictions.ollamaDownBanner') || 'Ollama has been unreachable for {min} minutes. AI features are degraded — users see cached predictions.')
                .replace('{min}', settings.ollama_downtime.duration_min)}
            </p>
            {settings.ollama_downtime.since && (
              <p className="text-xs text-red-500/70">
                {(t('aiPredictions.ollamaOfflineSince') || 'Offline since {date}')
                  .replace('{date}', new Date(settings.ollama_downtime.since).toLocaleString())}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Status overview */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-accent)]">{Icons.cpu}</span>
            <span className="text-sm font-medium">
              {t('aiPredictions.statusPanel') || 'AI Predictions Status'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={testing ? 'loading' : (testResult?.status || displayStatus)} />
            <button
              onClick={loadSettings}
              title="Refresh"
              className="p-1 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-bg-secondary)] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>

        {/* Config row */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-[var(--color-bg-card)] rounded-lg p-2">
            <p className="text-[var(--color-text-muted)] mb-0.5">
              {t('aiPredictions.configuredModel') || 'Model'}
            </p>
            <p className="font-medium truncate">
              {activeResult.current_model || settings.ollama_live?.current_model || '—'}
            </p>
          </div>
          <div className="bg-[var(--color-bg-card)] rounded-lg p-2">
            <p className="text-[var(--color-text-muted)] mb-0.5">
              {t('aiPredictions.lastChecked') || 'Last checked'}
            </p>
            <p className="font-medium">
              {formatRelativeTime(activeResult.checked_at || live.checked_at) || '—'}
            </p>
          </div>
        </div>

        {/* URL */}
        {settings.ollama_url && (
          <div className="text-xs text-[var(--color-text-muted)] truncate">
            {settings.ollama_url}
          </div>
        )}

        {/* Message on error/offline */}
        {(activeResult.message) && (
          <div className="flex items-start gap-2 text-xs text-yellow-600 dark:text-yellow-400">
            {Icons.info}
            <span>{activeResult.message}</span>
          </div>
        )}
      </div>

      {/* Available models */}
      {models.length > 0 && (
        <div>
          <button
            onClick={() => setShowModels(!showModels)}
            className="flex items-center gap-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors mb-2"
          >
            {showModels ? Icons.chevronUp : Icons.chevronDown}
            {t('aiPredictions.availableModels') || 'Available Models'} ({models.length})
          </button>
          {showModels && (
            <div className="space-y-1.5">
              {models.map((m) => {
                const isCurrent = m.name === (live.current_model || settings.ollama_live?.current_model)
                return (
                  <div
                    key={m.name}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs ${
                      isCurrent
                        ? 'bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30'
                        : 'bg-[var(--color-bg-tertiary)]'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {isCurrent && (
                        <span className="text-[var(--color-accent)]">{Icons.check}</span>
                      )}
                      <span className={`font-mono ${isCurrent ? 'font-semibold text-[var(--color-accent)]' : ''}`}>
                        {m.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[var(--color-text-muted)]">
                      {formatBytes(m.size) && <span>{formatBytes(m.size)}</span>}
                      {m.digest && <span className="font-mono opacity-60">{m.digest}</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {models.length === 0 && displayStatus === 'online' && (
        <p className="text-xs text-[var(--color-text-muted)] text-center py-2">
          {t('aiPredictions.noModels') || 'No models loaded in Ollama'}
        </p>
      )}

      {/* Prediction stats */}
      <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4">
        <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide mb-3">
          {t('aiPredictions.predictionStats') || 'Prediction Statistics'}
        </p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-[var(--color-bg-card)] rounded-lg p-2">
            <p className="text-lg font-bold text-[var(--color-accent)]">{stats.total ?? '—'}</p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('aiPredictions.totalPredictions') || 'Total'}
            </p>
          </div>
          <div className="bg-[var(--color-bg-card)] rounded-lg p-2">
            <p className="text-lg font-bold text-orange-500">{stats.active ?? '—'}</p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('aiPredictions.activePredictions') || 'Active'}
            </p>
          </div>
          <div className="bg-[var(--color-bg-card)] rounded-lg p-2">
            <p className="text-xs font-semibold">
              {formatRelativeTime(stats.last_generated_at) || (t('aiPredictions.neverGenerated') || 'Never')}
            </p>
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('aiPredictions.lastGenerated') || 'Last run'}
            </p>
          </div>
        </div>
      </div>

      {/* AI response cache */}
      {settings?.ollama_enabled && (
        <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide">
              {t('aiPredictions.cacheTitle') || 'AI Response Cache'}
            </p>
            {settings?.ai_cache?.available && (
              <span className="text-xs text-[var(--color-text-muted)]">
                {(t('aiPredictions.cacheKeys') || '{n} key(s) cached').replace('{n}', settings.ai_cache.keys)}
              </span>
            )}
          </div>

          <p className="text-xs text-[var(--color-text-muted)]">
            {t('aiPredictions.cacheHint') || 'Ollama responses are cached in Redis to avoid redundant calls. Flush when you change models or want immediate fresh results.'}
          </p>

          {!settings?.ai_cache?.available && (
            <div className="flex items-start gap-2 p-2 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
              <span className="text-yellow-500 shrink-0">{Icons.info}</span>
              <span className="text-xs text-yellow-600 dark:text-yellow-400">
                {t('aiPredictions.cacheUnavailable') || 'Redis is unavailable — caching is disabled.'}
              </span>
            </div>
          )}

          {flushMsg && (
            <p className={`text-xs ${flushMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
              {flushMsg.text}
            </p>
          )}

          <button
            onClick={handleFlushCache}
            disabled={flushingCache || !settings?.ai_cache?.available}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-500/20 disabled:opacity-40 transition-colors border border-red-500/20"
          >
            {flushingCache ? (
              <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            )}
            {t('aiPredictions.flushCache') || 'Flush AI Cache'}
          </button>
        </div>
      )}

      {/* Task Model Assignment */}
      {settings?.ollama_enabled && (
        <div className="bg-[var(--color-bg-tertiary)] rounded-xl p-4 space-y-3">
          <p className="text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide">
            {t('aiPredictions.taskModels') || 'Task Model Assignment'}
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">
            {t('aiPredictions.taskModelsHint') || 'Choose which locally-available model to use for each AI task. Leave blank to use the default model.'}
          </p>

          {/* Warning: no model configured at all */}
          {!taskModels.global && !settings?.ollama_live?.current_model && (
            <div className="flex items-start gap-2 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
              <span className="text-yellow-500 mt-0.5 shrink-0">{Icons.info}</span>
              <span className="text-xs text-yellow-600 dark:text-yellow-400">
                {t('aiPredictions.noModelConfigured') || 'No AI model is selected. Run \u2018ollama list\u2019 to see your available models, then choose one as the Global Default above.'}
              </span>
            </div>
          )}

          {[
            { key: 'global',   label: t('aiPredictions.modelGlobal')   || 'Global Default (all tasks)' },
            { key: 'predict',  label: t('aiPredictions.modelPredict')  || 'Maintenance Predictions' },
            { key: 'ocr',      label: t('aiPredictions.modelOcr')      || 'Receipt OCR' },
            { key: 'anomaly',  label: t('aiPredictions.modelAnomaly')  || 'Fuel Anomaly Detection' },
            { key: 'reminder', label: t('aiPredictions.modelReminder') || 'Reminder Drafting' },
          ].map(({ key, label }) => (
            <div key={key} className={`flex flex-col gap-1 ${key === 'global' ? 'pb-3 mb-1 border-b border-[var(--color-border)]' : ''}`}>
              <label className="text-xs font-medium text-[var(--color-text)]">
                {label}
                {key === 'global' && (
                  <span className="ml-2 text-2xs font-normal text-[var(--color-text-muted)]">
                    {t('aiPredictions.modelGlobalHint') || '— used when no task-specific model is set'}
                  </span>
                )}
              </label>
              <select
                value={taskModels[key] || ''}
                onChange={e => setTaskModels(prev => ({ ...prev, [key]: e.target.value }))}
                className="w-full text-xs bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-lg px-2.5 py-1.5 text-[var(--color-text)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
              >
                <option value="">{key === 'global' ? (t('aiPredictions.selectModel') || '— select a model —') : (t('aiPredictions.useGlobalDefault') || 'Use global default')}</option>
                {(settings?.ollama_live?.models || []).map(m => (
                  <option key={m.name} value={m.name}>{m.name}{m.size ? ` — ${formatBytes(m.size)}` : ''}</option>
                ))}
              </select>
            </div>
          ))}

          {modelSaveMsg && (
            <p className={`text-xs ${modelSaveMsg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
              {modelSaveMsg.text}
            </p>
          )}

          <button
            onClick={handleSaveModels}
            disabled={savingModels}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium bg-[var(--color-accent)]/10 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/20 disabled:opacity-50 transition-colors border border-[var(--color-accent)]/30"
          >
            {savingModels ? (
              <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              Icons.check
            )}
            {t('aiPredictions.saveModels') || 'Save Model Settings'}
          </button>
        </div>
      )}

      {/* Test connection button */}
      <button
        onClick={handleTest}
        disabled={testing || !settings.ollama_enabled}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium bg-[var(--color-accent)] text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        {testing ? (
          <>
            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            {t('aiPredictions.testing') || 'Testing…'}
          </>
        ) : (
          <>
            {Icons.refresh}
            {t('aiPredictions.testConnection') || 'Test Connection'}
          </>
        )}
      </button>

      {!settings.ollama_enabled && (
        <p className="text-xs text-center text-[var(--color-text-muted)]">
          {t('aiPredictions.disabled') || 'AI predictions are not enabled on this server.'}
        </p>
      )}
    </div>
  )
}
