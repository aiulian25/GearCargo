import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useBlocker } from 'react-router-dom'
import { UnsavedChangesContext } from '../contexts/UnsavedChangesContext'
import { useTranslation } from '../contexts/LanguageContext'
import { useConfirm } from './ui/ConfirmDialog'

// One router blocker serves every registered form, including history POPs and
// links outside the form. Keep the form mounted until the user chooses to leave.
export default function UnsavedChangesProvider({ children }) {
  const guards = useRef(new Set())
  const pending = useRef(null)
  const confirm = useConfirm()
  const { t } = useTranslation()
  const shouldBlock = useCallback(() => [...guards.current].some(guard => guard()), [])
  const blocker = useBlocker(shouldBlock)
  const latestBlocker = useRef(blocker)
  latestBlocker.current = blocker

  const cancelPending = useCallback(() => {
    pending.current?.abort()
    pending.current = null
    if (latestBlocker.current.state === 'blocked') latestBlocker.current.reset()
  }, [])
  const register = useCallback(guard => {
    guards.current.add(guard)
    return () => guards.current.delete(guard)
  }, [])
  const saved = useCallback(() => {
    // A successful save can finish while a navigation dialog is open. Its own
    // return navigation wins; never resume an obsolete blocked destination.
    if (!shouldBlock()) cancelPending()
  }, [shouldBlock, cancelPending])
  const confirmExit = useCallback(async () => {
    if (!shouldBlock()) return true
    cancelPending()
    const controller = new AbortController()
    pending.current = controller
    const discard = await confirm({ title: t('unsavedChanges.title'), message: t('unsavedChanges.message'),
      confirmLabel: t('unsavedChanges.discard'), cancelLabel: t('unsavedChanges.stay'),
      destructive: true, signal: controller.signal })
    if (controller.signal.aborted) return false
    pending.current = null
    return discard
  }, [shouldBlock, cancelPending, confirm, t])
  const context = useMemo(() => ({ register, saved, confirmExit }), [register, saved, confirmExit])

  useEffect(() => {
    if (blocker.state !== 'blocked' || pending.current) return
    const controller = new AbortController()
    pending.current = controller
    confirm({ title: t('unsavedChanges.title'), message: t('unsavedChanges.message'),
      confirmLabel: t('unsavedChanges.discard'), cancelLabel: t('unsavedChanges.stay'),
      destructive: true, signal: controller.signal,
    }).then(discard => {
      if (controller.signal.aborted) return
      pending.current = null
      const current = latestBlocker.current
      if (current.state !== 'blocked') return
      if (discard) current.proceed()
      else current.reset()
    })
  }, [blocker, confirm, t])

  // Account/session remounts cancel the old dialog and release references to
  // private form state. They must not be vetoed by another account's form.
  useEffect(() => () => { pending.current?.abort(); guards.current.clear() }, [])

  return <UnsavedChangesContext.Provider value={context}>{children}</UnsavedChangesContext.Provider>
}
