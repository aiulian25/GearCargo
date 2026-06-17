/**
 * GearCargo - Push Permission Priming Modal
 *
 * Shown BEFORE the browser's one-shot permission prompt to explain the value
 * of push notifications. Only "Enable" proceeds to the OS prompt, so we never
 * burn the permission on an undecided user. Keyboard-accessible (Esc closes,
 * primary action auto-focused) and responsive.
 */

import { useEffect, useRef } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'

const BellIcon = (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
  </svg>
)

const CheckIcon = (
  <svg className="w-5 h-5 shrink-0 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
)

export default function PushPrimingModal({ isOpen, onConfirm, onClose }) {
  const { t } = useTranslation()
  const confirmRef = useRef(null)

  // Esc to close + focus the primary action on open.
  useEffect(() => {
    if (!isOpen) return
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', handleKey)
    confirmRef.current?.focus()
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const benefits = [
    t('settings.pushBenefitReminders'),
    t('settings.pushBenefitExpiry'),
    t('settings.pushBenefitSecurity'),
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="push-priming-title"
        className="w-full max-w-md bg-[var(--color-bg-card)] rounded-2xl shadow-xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-2 flex items-start gap-4">
          <div className="shrink-0 w-12 h-12 rounded-xl bg-[var(--color-accent)]/15 text-[var(--color-accent)] flex items-center justify-center">
            {BellIcon}
          </div>
          <div className="flex-1 min-w-0">
            <h2 id="push-priming-title" className="text-lg font-semibold text-[var(--color-text-primary)]">
              {t('settings.pushPrimingTitle')}
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] mt-1">
              {t('settings.pushPrimingDesc')}
            </p>
          </div>
        </div>

        {/* Benefits */}
        <ul className="px-6 py-4 space-y-2.5">
          {benefits.map((benefit, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-[var(--color-text-primary)]">
              {CheckIcon}
              <span className="min-w-0">{benefit}</span>
            </li>
          ))}
        </ul>

        <p className="px-6 text-xs text-[var(--color-text-muted)]">
          {t('settings.pushPrimingPrivacy')}
        </p>

        {/* Actions */}
        <div className="px-6 py-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 rounded-lg text-sm font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          >
            {t('pwa.notNow')}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className="px-4 py-2.5 rounded-lg text-sm font-medium bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2 focus:ring-offset-[var(--color-bg-card)]"
          >
            {t('settings.pushPrimingEnable')}
          </button>
        </div>
      </div>
    </div>
  )
}
