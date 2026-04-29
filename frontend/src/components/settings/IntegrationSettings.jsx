import { useState, useEffect } from 'react'
import { widgetApi } from '../../services/api'
import { useLanguage } from '../../contexts/LanguageContext'
import toast from 'react-hot-toast'

export default function IntegrationSettings() {
  const { t } = useLanguage()
  const [keyInfo, setKeyInfo] = useState({ hasKey: false, prefix: null })
  const [newKey, setNewKey] = useState(null)   // raw key shown ONCE after generation
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(null)

  useEffect(() => {
    const fetchKey = async () => {
      try {
        const res = await widgetApi.getApiKey()
        setKeyInfo({ hasKey: res.data.has_key, prefix: res.data.prefix })
      } catch {
        // No key yet
      } finally {
        setLoading(false)
      }
    }
    fetchKey()
  }, [])

  const handleGenerate = async () => {
    if (keyInfo.hasKey && !window.confirm(t('integrations.regenerateConfirm') || 'Regenerate API key? The old key will stop working.')) return
    setGenerating(true)
    try {
      const res = await widgetApi.generateApiKey()
      setKeyInfo({ hasKey: true, prefix: res.data.prefix })
      setNewKey(res.data.raw_key)
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
      setKeyInfo({ hasKey: false, prefix: null })
      setNewKey(null)
      toast.success(t('integrations.keyRevoked') || 'API key revoked')
    } catch {
      toast.error(t('integrations.revokeFailed') || 'Failed to revoke API key')
    }
  }

  const dismissNewKey = () => setNewKey(null)

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
  // Masked display uses the prefix + dots; raw key only shown immediately after generation
  const maskedKey = keyInfo.prefix ? `${keyInfo.prefix}${'•'.repeat(56)}` : null
  // For homepage config snippet, use raw key if freshly generated, else placeholder
  const configKey = newKey || (keyInfo.prefix ? `${keyInfo.prefix}••••••••••••••••••••••••••••••••••••••••••••••••••••••••` : '')

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

        {/* One-time new key banner — shown immediately after generation */}
        {newKey && (
          <div className="mb-3 rounded-lg border border-amber-400/40 bg-amber-50/10 p-3 space-y-2">
            <p className="text-xs font-medium text-amber-500 flex items-center gap-1">
              <span className="material-icons-outlined text-base">warning</span>
              {t('integrations.copyNowWarning') || 'Copy your key now — it will not be shown again.'}
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-[var(--color-bg-tertiary)] text-xs px-3 py-2 rounded-lg font-mono break-all select-all">
                {newKey}
              </code>
              <button
                onClick={() => copyToClipboard(newKey, 'newKey')}
                className="btn btn-ghost btn-sm flex-shrink-0"
                title="Copy"
              >
                <span className="material-icons-outlined text-sm">
                  {copied === 'newKey' ? 'check' : 'content_copy'}
                </span>
              </button>
            </div>
            <button onClick={dismissNewKey} className="text-2xs text-[var(--color-text-muted)] hover:underline">
              {t('integrations.gotIt') || 'I have copied the key'}
            </button>
          </div>
        )}

        {keyInfo.hasKey ? (
          <div className="space-y-2">
            {!newKey && (
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-[var(--color-bg-tertiary)] text-xs px-3 py-2 rounded-lg font-mono truncate text-[var(--color-text-muted)]">
                  {maskedKey}
                </code>
              </div>
            )}
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
      {keyInfo.hasKey && (
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
    icon: ${baseUrl}/icons/logo.png
    href: ${baseUrl}
    widget:
      type: customapi
      url: ${baseUrl}/api/widget/v1/homepage?key=${configKey}
      display: block
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
            {newKey && (
              <button
                onClick={() => copyToClipboard(`- GearCargo:\n    icon: ${baseUrl}/icons/logo.png\n    href: ${baseUrl}\n    widget:\n      type: customapi\n      url: ${baseUrl}/api/widget/v1/homepage?key=${newKey}\n      display: block\n      mappings:\n        - field: vehicles\n          label: Vehicles\n          format: number\n        - field: service_records\n          label: Service Records\n          format: number\n        - field: reminders\n          label: Reminders\n          format: number\n        - field: next_reminder\n          label: Next Reminder\n          format: text`, 'config')}
                className="absolute top-2 right-2 btn btn-ghost btn-sm"
                title="Copy config"
              >
                <span className="material-icons-outlined text-sm">
                  {copied === 'config' ? 'check' : 'content_copy'}
                </span>
              </button>
            )}
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

