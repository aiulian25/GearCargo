import { useState, useEffect } from 'react'
import { widgetApi } from '../../services/api'
import { useLanguage } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

export default function IntegrationSettings() {
  const { t } = useLanguage()
  const [apiKey, setApiKey] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(null)

  useEffect(() => {
    const fetchKey = async () => {
      try {
        const res = await widgetApi.getApiKey()
        setApiKey(res.data.api_key)
      } catch {
        // No key yet
      } finally {
        setLoading(false)
      }
    }
    fetchKey()
  }, [])

  const handleGenerate = async () => {
    if (apiKey && !window.confirm(t('integrations.regenerateConfirm') || 'Regenerate API key? The old key will stop working.')) return
    setGenerating(true)
    try {
      const res = await widgetApi.generateApiKey()
      setApiKey(res.data.api_key)
      toast.success(t('integrations.keyGenerated') || 'API key generated')
    } catch {
      toast.error(t('integrations.keyFailed') || 'Failed to generate API key')
    } finally {
      setGenerating(false)
    }
  }

  const handleRevoke = async () => {
    if (!window.confirm(t('integrations.revokeConfirm') || 'Revoke API key? External integrations will stop working.')) return
    try {
      await widgetApi.revokeApiKey()
      setApiKey(null)
      toast.success(t('integrations.keyRevoked') || 'API key revoked')
    } catch {
      toast.error(t('integrations.revokeFailed') || 'Failed to revoke API key')
    }
  }

  const copyToClipboard = async (text, label) => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.left = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      setCopied(label)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      toast.error('Failed to copy to clipboard')
    }
  }

  const baseUrl = window.location.origin

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="skeleton h-10 rounded-xl" />
        <div className="skeleton h-10 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* API Key Section */}
      <div>
        <h4 className="text-sm font-medium mb-2">{t('integrations.apiKey') || 'API Key'}</h4>
        <p className="text-2xs text-[var(--color-text-muted)] mb-3">
          {t('integrations.apiKeyDesc') || 'Used to authenticate external services like Gethomepage'}
        </p>

        {apiKey ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-[var(--color-bg-tertiary)] text-xs px-3 py-2 rounded-lg font-mono truncate">
                {apiKey}
              </code>
              <button
                onClick={() => copyToClipboard(apiKey, 'key')}
                className="btn btn-ghost btn-sm flex-shrink-0"
                title="Copy"
              >
                <span className="material-icons-outlined text-sm">
                  {copied === 'key' ? 'check' : 'content_copy'}
                </span>
              </button>
            </div>
            <div className="flex gap-2">
              <button onClick={handleGenerate} disabled={generating} className="btn btn-secondary btn-sm">
                {generating ? (t('common.loading') || 'Loading...') : (t('integrations.regenerate') || 'Regenerate')}
              </button>
              <button onClick={handleRevoke} className="btn btn-sm text-red-500 hover:bg-red-500/10">
                {t('integrations.revoke') || 'Revoke'}
              </button>
            </div>
          </div>
        ) : (
          <button onClick={handleGenerate} disabled={generating} className="btn btn-primary btn-sm">
            {generating ? (t('common.loading') || 'Loading...') : (t('integrations.generate') || 'Generate API Key')}
          </button>
        )}
      </div>

      {/* Gethomepage Config */}
      {apiKey && (
        <div>
          <h4 className="text-sm font-medium mb-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="material-icons-outlined text-base text-[var(--color-accent)]">dashboard</span>
              {t('integrations.gethomepage') || 'Gethomepage'}
            </span>
          </h4>
          <p className="text-2xs text-[var(--color-text-muted)] mb-3">
            {t('integrations.gethomepageDesc') || 'Add to your Gethomepage services.yaml:'}
          </p>

          <div className="relative">
            <pre className="bg-[var(--color-bg-tertiary)] text-xs px-3 py-3 rounded-lg font-mono overflow-x-auto whitespace-pre text-[var(--color-text-secondary)]">{`- GearCargo:
    icon: mdi-car
    href: ${baseUrl}
    widget:
      type: customapi
      url: ${baseUrl}/api/widget/v1/homepage
      headers:
        X-API-Key: ${apiKey}
      mappings:
        - field: vehicles
          label: Vehicles
          format: number
        - field: service_records
          label: Service Records
          format: number
        - field: reminders
          label: Reminders
          format: number
        - field: next_reminder
          label: Next Reminder
          format: text`}</pre>
            <button
              onClick={() => copyToClipboard(`- GearCargo:\n    icon: mdi-car\n    href: ${baseUrl}\n    widget:\n      type: customapi\n      url: ${baseUrl}/api/widget/v1/homepage\n      headers:\n        X-API-Key: ${apiKey}\n      mappings:\n        - field: vehicles\n          label: Vehicles\n          format: number\n        - field: service_records\n          label: Service Records\n          format: number\n        - field: reminders\n          label: Reminders\n          format: number\n        - field: next_reminder\n          label: Next Reminder\n          format: text`, 'config')}
              className="absolute top-2 right-2 btn btn-ghost btn-sm"
              title="Copy config"
            >
              <span className="material-icons-outlined text-sm">
                {copied === 'config' ? 'check' : 'content_copy'}
              </span>
            </button>
          </div>

          {/* Endpoint reference */}
          <div className="mt-3 space-y-1">
            <p className="text-2xs text-[var(--color-text-muted)]">
              {t('integrations.endpoints') || 'Available endpoints:'}
            </p>
            <div className="flex items-center gap-2">
              <code className="text-2xs bg-[var(--color-bg-tertiary)] px-2 py-1 rounded font-mono">
                GET /api/widget/v1/homepage
              </code>
              <button
                onClick={() => copyToClipboard(`${baseUrl}/api/widget/v1/homepage`, 'ep1')}
                className="btn btn-ghost p-0.5"
              >
                <span className="material-icons-outlined text-xs">
                  {copied === 'ep1' ? 'check' : 'content_copy'}
                </span>
              </button>
            </div>
            <div className="flex items-center gap-2">
              <code className="text-2xs bg-[var(--color-bg-tertiary)] px-2 py-1 rounded font-mono">
                GET /api/widget/v1/vehicles
              </code>
              <button
                onClick={() => copyToClipboard(`${baseUrl}/api/widget/v1/vehicles`, 'ep2')}
                className="btn btn-ghost p-0.5"
              >
                <span className="material-icons-outlined text-xs">
                  {copied === 'ep2' ? 'check' : 'content_copy'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
