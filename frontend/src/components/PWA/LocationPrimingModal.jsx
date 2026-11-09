/**
 * GearCargo - Location Consent Modal
 *
 * Shown BEFORE the browser's geolocation prompt. It names the third party that
 * receives the position, and only "Use my location" leads to the browser
 * prompt. Focus starts on the dialog itself, so a stray Enter shares nothing.
 */

import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import { LOCATION_SETTINGS_PATH, MANUAL_LOCATION_STATE_KEY } from '../../config/location'

const MapPinIcon = (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
  </svg>
)

// Tab and Shift+Tab cycle through the dialog's actions instead of reaching the page behind it.
function keepTabFocusInside(event, dialog, firstAction, lastAction) {
  const leavingBackwards = event.shiftKey && [dialog, firstAction].includes(document.activeElement)
  const leavingForwards = !event.shiftKey && document.activeElement === lastAction
  if (!leavingBackwards && !leavingForwards) return
  event.preventDefault()
  const nextAction = leavingBackwards ? lastAction : firstAction
  nextAction.focus()
}

export default function LocationPrimingModal({ isOpen, onConfirm, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const firstActionRef = useRef(null)
  const lastActionRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return
    const previouslyFocused = document.activeElement
    const handleKey = (event) => {
      if (event.key === 'Escape') onClose?.()
      if (event.key === 'Tab') keepTabFocusInside(event, dialogRef.current, firstActionRef.current, lastActionRef.current)
    }
    document.addEventListener('keydown', handleKey)
    dialogRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', handleKey)
      previouslyFocused?.focus?.()
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-priming-title"
        aria-describedby="location-priming-description"
        tabIndex={-1}
        className="w-full max-w-md bg-(--color-bg-card) rounded-2xl shadow-xl overflow-hidden flex flex-col focus:outline-hidden"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="px-6 pt-6 pb-2 flex items-start gap-4">
          <div className="shrink-0 w-12 h-12 rounded-xl bg-(--color-accent)/15 text-(--color-accent) flex items-center justify-center">
            {MapPinIcon}
          </div>
          <div className="flex-1 min-w-0">
            <h2 id="location-priming-title" className="text-lg font-semibold text-(--color-text-primary)">
              {t('locationConsent.title')}
            </h2>
            <p id="location-priming-description" className="text-sm text-(--color-text-muted) mt-1">
              {t('locationConsent.description')}
            </p>
          </div>
        </div>

        <p className="px-6 pt-2 text-xs text-(--color-text-muted)">
          {t('locationConsent.note')}
        </p>

        {/* Its own line: in Romanian and Spanish the three actions do not fit one row. */}
        <Link
          ref={firstActionRef}
          to={LOCATION_SETTINGS_PATH}
          state={{ [MANUAL_LOCATION_STATE_KEY]: true }}
          onClick={onClose}
          className="self-start mx-6 mt-2 py-1 text-sm font-medium text-(--color-accent) hover:underline rounded-sm focus:outline-hidden focus:ring-2 focus:ring-(--color-accent)"
        >
          {t('locationConsent.enterManually')}
        </Link>

        <div className="px-6 py-5 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 rounded-lg text-sm font-medium text-(--color-text-secondary) hover:bg-(--color-bg-tertiary) transition-colors focus:outline-hidden focus:ring-2 focus:ring-(--color-accent)"
          >
            {t('pwa.notNow')}
          </button>
          <button
            ref={lastActionRef}
            type="button"
            onClick={onConfirm}
            className="px-4 py-2.5 rounded-lg text-sm font-medium bg-(--color-accent) text-white hover:opacity-90 transition-opacity focus:outline-hidden focus:ring-2 focus:ring-(--color-accent) focus:ring-offset-2 focus:ring-offset-(--color-bg-card)"
          >
            {t('locationConsent.allow')}
          </button>
        </div>
      </div>
    </div>
  )
}
