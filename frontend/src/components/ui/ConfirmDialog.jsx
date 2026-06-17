import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

/**
 * Consistent, accessible confirmation dialog (IMPROVEMENTS.md §2).
 *
 * Replaces native window.confirm() with a themed, localized modal. Exposes an
 * imperative, promise-based API so call sites stay simple:
 *
 *   const confirm = useConfirm()
 *   if (!(await confirm({ title, message, confirmLabel, destructive: true }))) return
 *
 * Accessibility: role="dialog" + aria-modal, labelled/described, Escape and
 * backdrop cancel, focus moves to the SAFE (cancel) button on open for
 * destructive actions and is restored to the trigger on close, basic Tab focus
 * trap between the two buttons.
 */
const ConfirmContext = createContext(null)

export function ConfirmProvider({ children }) {
  const { t } = useTranslation()
  const [options, setOptions] = useState(null)
  const resolveRef = useRef(null)
  const cancelBtnRef = useRef(null)
  const confirmBtnRef = useRef(null)
  const prevFocusRef = useRef(null)

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      resolveRef.current = resolve
      prevFocusRef.current = document.activeElement
      setOptions(opts)
    })
  }, [])

  const settle = useCallback((result) => {
    setOptions(null)
    const resolve = resolveRef.current
    resolveRef.current = null
    // Restore focus to the element that opened the dialog.
    if (prevFocusRef.current && typeof prevFocusRef.current.focus === 'function') {
      prevFocusRef.current.focus()
    }
    if (resolve) resolve(result)
  }, [])

  // Focus management + keyboard handling while open.
  useEffect(() => {
    if (!options) return undefined
    // Safe default: focus Cancel for destructive dialogs, Confirm otherwise.
    const focusTarget = options.destructive === false ? confirmBtnRef.current : cancelBtnRef.current
    focusTarget?.focus()

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        settle(false)
      } else if (e.key === 'Tab') {
        // Minimal focus trap between the two buttons.
        const focusables = [cancelBtnRef.current, confirmBtnRef.current].filter(Boolean)
        if (focusables.length < 2) return
        const [first, last] = [focusables[0], focusables[focusables.length - 1]]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [options, settle])

  const o = options || {}
  const isDestructive = o.destructive !== false // destructive by default

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
            aria-hidden="true"
            onClick={() => settle(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby="confirm-dialog-message"
            className="relative w-full max-w-sm rounded-2xl bg-[var(--color-bg-card)] border border-[var(--color-border)] shadow-xl p-5"
          >
            <h2 id="confirm-dialog-title" className="text-base font-semibold mb-2 break-words">
              {o.title || t('confirm.defaultTitle') || 'Are you sure?'}
            </h2>
            {o.message && (
              <p id="confirm-dialog-message" className="text-sm text-[var(--color-text-secondary)] mb-5 leading-relaxed break-words">
                {o.message}
              </p>
            )}
            <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
              <button
                ref={cancelBtnRef}
                type="button"
                onClick={() => settle(false)}
                className="px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] text-sm font-medium hover:opacity-90"
              >
                {o.cancelLabel || t('common.cancel') || 'Cancel'}
              </button>
              <button
                ref={confirmBtnRef}
                type="button"
                onClick={() => settle(true)}
                className={`px-4 py-2 rounded-lg text-sm font-medium text-white ${
                  isDestructive ? 'bg-red-500 hover:bg-red-600' : 'bg-[var(--color-accent)] hover:opacity-90'
                }`}
              >
                {o.confirmLabel || t('common.confirm') || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) {
    // Fail safe: degrade to native confirm if the provider is missing.
    return (opts = {}) => Promise.resolve(window.confirm(opts.message || opts.title || ''))
  }
  return ctx
}

export default ConfirmProvider
