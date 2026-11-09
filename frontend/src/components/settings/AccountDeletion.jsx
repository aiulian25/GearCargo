import { useId, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { authApi } from '../../services/api'
import { useAuth } from '../../contexts/AuthContext'
import { useTranslation } from '../../contexts/LanguageContext'
import { useBackgroundSync } from '../../hooks/useBackgroundSync'
import { notifyPendingCleanup } from '../../utils/deletionFeedback'
import { serverMessage } from '../../utils/serverMessage'

const AUTHENTICATOR_CODE_PATTERN = /^\d{6}$/
const SIGN_IN_PATH = '/login'
const OFFLINE_CHANGES_PATH = '/settings#offline-changes'
const TOO_MANY_REQUESTS_STATUS = 429
const SERVICE_UNAVAILABLE_STATUS = 503
const AUTH_UNAVAILABLE_CODE = 'AUTH_UNAVAILABLE'
const CODE_INVALID_MESSAGE_KEY = 'profile.deleteAccountCodeInvalid'

// Six digits are an authenticator code; anything else is tried as a backup code.
function secondFactorFields(code) {
  const value = code.trim()
  if (!value) return {}
  return AUTHENTICATOR_CODE_PATTERN.test(value) ? { totp_code: value } : { backup_code: value }
}

// This 503 arrives either before the deletion ran or after it committed, when
// saving the browser session failed. Staying signed in is right either way: once
// the account is gone, the next request fails and the client signs out.
function deletionMayHaveCommitted(requestError) {
  const response = requestError?.response
  return response?.status === SERVICE_UNAVAILABLE_STATUS && response.data?.code === AUTH_UNAVAILABLE_CODE
}

function refusalMessage(requestError, t) {
  const response = requestError?.response
  if (response?.status === TOO_MANY_REQUESTS_STATUS) return t('profile.deleteAccountTooManyAttempts')
  if (deletionMayHaveCommitted(requestError)) return t('profile.deleteAccountMayHaveCompleted')
  // The instance-wide deletion lease was busy: other requests or a restore were running.
  if (response?.status === SERVICE_UNAVAILABLE_STATUS && response.data?.recovery) return t('profile.deleteAccountBusy')
  return serverMessage(requestError, t)
}

// Its own component so the hook's 30-second sync loop runs only while the form is open.
function UnsentDraftsHint() {
  const { t } = useTranslation()
  const { hasPendingSync, pausedCount, receiptCount } = useBackgroundSync()
  const hasUnsentDrafts = hasPendingSync || pausedCount > 0 || receiptCount > 0
  if (!hasUnsentDrafts) return null
  return (
    <p className="text-xs text-amber-500">
      {t('profile.deleteAccountUnsentDrafts')}{' '}
      <a href={OFFLINE_CHANGES_PATH} className="underline">{t('pwa.sync.pausedBadge')}</a>
    </p>
  )
}

export default function AccountDeletion() {
  const { t } = useTranslation()
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const passwordId = useId()
  const codeId = useId()
  const descriptionId = useId()
  const openerRef = useRef(null)

  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  const requiresCode = Boolean(user?.two_factor_enabled)
  const incomplete = !password || (requiresCode && !code.trim())

  const cancel = () => {
    // Render the Delete Account button again before handing focus back to it.
    flushSync(() => {
      setOpen(false)
      setPassword('')
      setCode('')
      setError('')
    })
    openerRef.current?.focus()
  }

  const signOutHere = async () => {
    try {
      await logout({ sessionEndedByServer: true })
    } finally {
      navigate(SIGN_IN_PATH, { replace: true })
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setDeleting(true)
    let response
    try {
      response = await authApi.deleteAccount({ password, ...secondFactorFields(code) })
    } catch (requestError) {
      setError(refusalMessage(requestError, t))
      // Two-factor sign-in was turned on elsewhere; reload it so the code field appears.
      const codeFieldMissing = !requiresCode && requestError?.response?.data?.message_key === CODE_INVALID_MESSAGE_KEY
      if (codeFieldMissing) await refreshUser()
      setDeleting(false)
      return
    }
    if (!notifyPendingCleanup(response, t)) toast.success(t('profile.accountDeleted'))
    await signOutHere()
  }

  return (
    <div className="card">
      <h3 className="text-sm font-medium text-red-500 mb-3">{t('profile.dangerZone')}</h3>

      {!open && (
        <>
          <button
            ref={openerRef}
            type="button"
            onClick={() => setOpen(true)}
            className="btn w-full border-red-500 text-red-500 hover:bg-red-500/10 text-sm"
          >
            {t('profile.deleteAccount')}
          </button>
          <p className="text-2xs text-(--color-text-muted) mt-2 text-center">{t('profile.cannotBeUndone')}</p>
        </>
      )}

      {open && (
        <form onSubmit={handleSubmit} className="space-y-3">
          <div id={descriptionId} className="space-y-3">
            <p className="text-xs text-(--color-text-secondary)">{t('profile.deleteAccountDescription')}</p>
            <UnsentDraftsHint />
          </div>
          {error && <p role="alert" className="text-sm text-red-500">{error}</p>}

          <div>
            <label htmlFor={passwordId} className="block text-xs text-(--color-text-muted) mb-1">
              {t('common.password')}
            </label>
            <input
              id={passwordId}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder={t('twoFactor.enterPassword')}
              className="input w-full"
              aria-describedby={descriptionId}
              autoFocus
              required
            />
          </div>

          {requiresCode && (
            <div>
              <label htmlFor={codeId} className="block text-xs text-(--color-text-muted) mb-1">
                {t('twoFactor.disableCodeLabel')}
              </label>
              <input
                id={codeId}
                type="text"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                autoComplete="one-time-code"
                autoCapitalize="characters"
                autoCorrect="off"
                spellCheck={false}
                placeholder={t('twoFactor.codeOrBackupPlaceholder')}
                className="input w-full font-mono tracking-wider"
                required
              />
              <p className="text-2xs text-(--color-text-muted) mt-1">{t('twoFactor.disableCodeHint')}</p>
            </div>
          )}

          <div className="flex gap-3">
            <button type="button" onClick={cancel} disabled={deleting} className="btn btn-secondary flex-1">
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={deleting || incomplete}
              className="btn bg-red-500 text-white hover:bg-red-600 flex-1"
            >
              {deleting ? t('profile.deletingAccount') : t('profile.deleteAccountConfirm')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
