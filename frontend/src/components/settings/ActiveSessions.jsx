import { useCallback, useEffect, useRef, useState } from 'react'
import { authApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useDateFormat } from '../../hooks/useDateFormat'
import { useConfirm } from '../ui/ConfirmDialog'
import { serverMessage } from '../../utils/serverMessage'

const DEVICE_LABEL_SEPARATOR = ' · '

export default function ActiveSessions() {
  const { t } = useTranslation()
  const { formatDateTime } = useDateFormat()
  const confirm = useConfirm()
  const heading = useRef(null)

  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await authApi.getSessions()
      setSessions(Array.isArray(data?.sessions) ? data.sessions : [])
    } catch (requestError) {
      setError(serverMessage(requestError, t))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    load()
  }, [load])

  const deviceLabel = (session) =>
    [session.browser, session.os].filter(Boolean).join(DEVICE_LABEL_SEPARATOR) || t('profile.unknownDevice')

  // Reload whatever the outcome: another device can refresh and change the list meanwhile.
  const confirmThenRun = async (confirmation, request, successKey) => {
    setError('')
    setNotice('')
    const confirmed = await confirm({ ...confirmation, destructive: true })
    if (!confirmed) return
    try {
      await request()
      setNotice(t(successKey))
    } catch (requestError) {
      setError(serverMessage(requestError, t))
    }
    await load()
    // The reload can remove the button that had focus.
    heading.current?.focus()
  }

  const signOutSession = (session) => {
    const device = deviceLabel(session)
    return confirmThenRun({
      title: t('profile.signOutSessionTitle', { device }),
      message: t('profile.signOutSessionConfirm'),
      confirmLabel: t('profile.signOutSession'),
    }, () => authApi.revokeSession(session.id), 'profile.sessionSignedOut')
  }

  const signOutOtherDevices = () => confirmThenRun({
    title: t('profile.logoutOtherDevicesTitle'),
    message: t('profile.logoutOtherDevicesConfirm'),
    confirmLabel: t('profile.logoutOtherDevices'),
  }, authApi.revokeOtherSessions, 'profile.otherDevicesSignedOut')

  if (loading) return null

  const hasOtherSessions = sessions.some((session) => !session.is_current)
  const onlyThisDevice = sessions.length > 0 && !hasOtherSessions

  return (
    <div className="card">
      <h3 ref={heading} tabIndex={-1} className="text-sm font-medium mb-3">{t('profile.activeSessions')}</h3>

      {error && <p role="alert" className="mb-3 text-sm text-red-500">{error}</p>}
      {notice && <p role="status" className="mb-3 text-sm text-green-500">{notice}</p>}

      <ul className="space-y-3">
        {sessions.map((session) => (
          <li key={session.id} className="flex items-center gap-3 p-2 bg-(--color-bg-tertiary) rounded-lg">
            <span
              aria-hidden="true"
              className={`material-icons-outlined icon-sm ${session.is_current ? 'text-green-500' : 'text-(--color-text-muted)'}`}
            >
              devices
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{deviceLabel(session)}</p>
              <p className="text-2xs text-(--color-text-muted)">
                {session.is_current
                  ? t('profile.currentDevice')
                  : t('profile.lastActive', { date: formatDateTime(session.last_active_at) })}
              </p>
              <p className="text-2xs text-(--color-text-muted)">
                {t('profile.sessionEnds', { date: formatDateTime(session.expires_at) })}
              </p>
            </div>
            {!session.is_current && (
              <button
                type="button"
                onClick={() => signOutSession(session)}
                aria-label={t('profile.signOutDevice', { device: deviceLabel(session) })}
                className="btn btn-ghost text-red-500 text-xs"
              >
                {t('profile.signOutSession')}
              </button>
            )}
          </li>
        ))}
      </ul>

      {hasOtherSessions && (
        <button type="button" onClick={signOutOtherDevices} className="btn btn-ghost w-full mt-4 text-red-500 text-sm">
          {t('profile.logoutOtherDevices')}
        </button>
      )}
      {onlyThisDevice && (
        <p className="text-2xs text-(--color-text-muted) mt-4 text-center">{t('profile.noOtherSessions')}</p>
      )}
    </div>
  )
}
