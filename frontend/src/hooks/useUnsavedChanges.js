import { useEffect } from 'react'

/**
 * Warn before leaving the page (tab close / reload / PWA dismiss / back gesture
 * to a different origin) while a form has unsaved changes.
 *
 * Usage: pass react-hook-form's `formState.isDirty`:
 *   const { formState: { isDirty } } = useForm(...)
 *   useUnsavedChanges(isDirty)
 *
 * Notes:
 * - Modern browsers display their OWN generic confirmation text for the
 *   `beforeunload` event and ignore custom strings, so this needs no
 *   translatable copy.
 * - In-app (client-side) navigation blocking would require migrating the app to
 *   a react-router data router (createBrowserRouter + useBlocker); that is a
 *   larger change tracked as a follow-up. This guard already covers the most
 *   common data-loss cases on mobile/PWA: accidental refresh, tab/app close, and
 *   OS back-to-previous-app.
 */
export function useUnsavedChanges(when) {
  useEffect(() => {
    if (!when) return undefined
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = '' // Chrome requires returnValue to be set to trigger the prompt
      return ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [when])
}

export default useUnsavedChanges
