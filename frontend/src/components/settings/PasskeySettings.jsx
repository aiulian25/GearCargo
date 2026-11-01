/**
 * Passkey management.
 *
 * A passkey signs in with the device's own lock instead of a password and a
 * code. The server decides whether this deployment can offer them at all (a
 * site reached by a bare address cannot), so the panel asks rather than
 * guesses, and explains itself when the answer is no.
 */
import { useCallback, useEffect, useState } from 'react'
import { startRegistration, browserSupportsWebAuthn } from '@simplewebauthn/browser'
import api from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useDateFormat } from '../../hooks/useDateFormat'
import { useConfirm } from '../ui/ConfirmDialog'

export default function PasskeySettings() {
  const { t } = useTranslation()
  const { formatDate } = useDateFormat()
  const confirm = useConfirm()

  const [serverAllows, setServerAllows] = useState(false)
  const [passkeys, setPasskeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const browserAllows = browserSupportsWebAuthn()

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/passkeys')
      setServerAllows(Boolean(data?.available))
      setPasskeys(Array.isArray(data?.passkeys) ? data.passkeys : [])
    } catch {
      setServerAllows(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const messageFrom = (requestError, fallbackKey) => {
    const body = requestError?.response?.data
    return (body?.message_key && t(body.message_key)) || body?.error || t(fallbackKey)
  }

  const addPasskey = async () => {
    setError('')
    setNotice('')
    setAdding(true)
    try {
      const { data: options } = await api.post('/auth/passkeys/options')
      const credential = await startRegistration({ optionsJSON: options })
      const { data } = await api.post('/auth/passkeys', { credential })
      setPasskeys((current) => [...current, data.passkey])
      setNotice(t('passkeys.added'))
    } catch (requestError) {
      // A person who dismisses the browser prompt has not hit an error.
      if (requestError?.name === 'NotAllowedError' || requestError?.name === 'AbortError') {
        setAdding(false)
        return
      }
      setError(messageFrom(requestError, 'passkeys.errorNotAdded'))
    } finally {
      setAdding(false)
    }
  }

  const removePasskey = async (passkey) => {
    setError('')
    setNotice('')
    const confirmed = await confirm({
      title: t('passkeys.removeTitle'),
      message: t('passkeys.removeConfirm', { name: passkey.name }),
      confirmLabel: t('passkeys.remove'),
      destructive: true,
    })
    if (!confirmed) return
    try {
      await api.delete(`/auth/passkeys/${passkey.id}`)
      setPasskeys((current) => current.filter((row) => row.id !== passkey.id))
      setNotice(t('passkeys.removed'))
    } catch (requestError) {
      setError(messageFrom(requestError, 'passkeys.errorNotFound'))
    }
  }

  if (loading) return null

  const usable = serverAllows && browserAllows

  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-(--color-text-primary)">
        {t('passkeys.title')}
      </h3>
      <p className="mt-1 text-sm text-(--color-text-muted)">{t('passkeys.description')}</p>

      {!usable && (
        <p className="mt-3 text-sm text-(--color-text-muted)" role="status">
          {serverAllows ? t('passkeys.unavailableBrowser') : t('passkeys.unavailableHere')}
        </p>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-500" role="alert">{error}</p>
      )}
      {notice && (
        <p className="mt-3 text-sm text-green-500" role="status">{notice}</p>
      )}

      {passkeys.length > 0 && (
        <ul className="mt-4 divide-y divide-(--color-border)">
          {passkeys.map((passkey) => (
            <li key={passkey.id} className="flex items-center justify-between gap-3 py-3">
              <span className="min-w-0">
                <span className="block truncate text-(--color-text-primary)">{passkey.name}</span>
                <small className="block text-xs text-(--color-text-muted)">
                  {passkey.last_used_at
                    ? t('passkeys.lastUsed', { date: formatDate(passkey.last_used_at) })
                    : t('passkeys.neverUsed')}
                  {passkey.other_relying_party
                    ? ` · ${t('passkeys.madeForOtherAddress', { host: passkey.other_relying_party })}`
                    : ''}
                </small>
              </span>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => removePasskey(passkey)}
              >
                {t('passkeys.remove')}
              </button>
            </li>
          ))}
        </ul>
      )}

      {passkeys.length === 0 && usable && (
        <p className="mt-4 text-sm text-(--color-text-muted)">{t('passkeys.empty')}</p>
      )}

      <button
        type="button"
        className="btn btn-primary mt-4"
        onClick={addPasskey}
        disabled={!usable || adding}
      >
        {adding ? t('passkeys.adding') : t('passkeys.add')}
      </button>

    </div>
  )
}
