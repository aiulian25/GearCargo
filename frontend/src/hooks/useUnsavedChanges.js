import { useCallback, useContext, useLayoutEffect, useRef } from 'react'
import { UnsavedChangesContext } from '../contexts/UnsavedChangesContext'

/** Register all unsaved state, including files/custom controls outside RHF.
 * Call the returned markSaved() only after the server or durable offline store
 * acknowledges the complete save, immediately before the existing navigation.
 * No draft is persisted: staying preserves the mounted form and selected files.
 */
export function useUnsavedChanges(when) {
  const context = useContext(UnsavedChangesContext)
  const active = useRef(false)
  const dirty = useRef(false)
  const saved = useRef(false)
  dirty.current = Boolean(when)
  const shouldBlock = useCallback(() => dirty.current && !saved.current, [])

  useLayoutEffect(() => {
    active.current = true
    const unregister = context?.register(shouldBlock)
    const beforeUnload = event => {
      if (!shouldBlock()) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => {
      active.current = false
      unregister?.()
      window.removeEventListener('beforeunload', beforeUnload)
    }
  }, [context, shouldBlock])

  return useCallback(() => {
    // Synchronous ref update avoids prompting when navigate follows in the
    // same tick, before React has rendered a reset formState.isDirty value.
    if (!active.current) return false
    saved.current = true
    context?.saved()
    return true
  }, [context])
}

export default useUnsavedChanges
