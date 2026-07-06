import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from '../../contexts/LanguageContext'
import AssistantChat from './AssistantChat'

/**
 * Dashboard AI assistant modal. Hosts the reusable AssistantChat. The chat is
 * per-vehicle server-side, so when the user has more than one vehicle we show a
 * selector in the chat header (defaults to the first vehicle).
 *
 * Dismissal: clicking the backdrop or pressing Escape closes it; clicks inside
 * the panel never bubble to the backdrop, so typing/sending never dismisses it.
 */
export default function ChatModal({ open, onClose, vehicles = [] }) {
  const { t } = useTranslation()
  const [selectedId, setSelectedId] = useState(null)

  // Default to the first vehicle each time the modal opens.
  useEffect(() => {
    if (open && vehicles.length > 0) {
      setSelectedId((prev) => (prev != null && vehicles.some((v) => v.id === prev) ? prev : vehicles[0].id))
    }
  }, [open, vehicles])

  // Escape closes; lock body scroll while open.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose])

  if (!open) return null

  const label = (v) => v.name || [v.year, v.make, v.model].filter(Boolean).join(' ') || `#${v.id}`

  const selector = vehicles.length > 1 ? (
    <div className="mt-0.5">
      <label htmlFor="chat-vehicle" className="sr-only">{t('chat.selectVehicle') || 'Chat about'}</label>
      <select
        id="chat-vehicle"
        value={selectedId ?? ''}
        onChange={(e) => setSelectedId(Number(e.target.value))}
        className="text-2xs bg-transparent text-[var(--color-text-muted)] border-none p-0 pr-4 -ml-0.5 focus:ring-0 focus:outline-none cursor-pointer max-w-[12rem] truncate"
      >
        {vehicles.map((v) => (
          <option key={v.id} value={v.id}>{label(v)}</option>
        ))}
      </select>
    </div>
  ) : null

  return (
    <div className="fixed inset-0 z-[130] flex items-end sm:items-center justify-center sm:p-4">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[1px]" aria-hidden="true" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('chat.title') || 'Vehicle Assistant'}
        className="relative w-full sm:max-w-lg h-[85vh] sm:h-[600px] sm:max-h-[85vh] bg-[var(--color-bg-primary)] rounded-t-2xl sm:rounded-2xl border border-[var(--color-border)] shadow-2xl overflow-hidden flex flex-col"
      >
        {vehicles.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-10 gap-4">
            <span className="text-4xl" aria-hidden="true">🤖</span>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {t('chat.noVehicles') || 'Add a vehicle to start chatting with the assistant.'}
            </p>
            <Link to="/vehicles/add" onClick={onClose} className="btn btn-primary">
              {t('dashboard.addVehicle') || 'Add Vehicle'}
            </Link>
            <button type="button" onClick={onClose} className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
              {t('common.close') || 'Close'}
            </button>
          </div>
        ) : (
          <AssistantChat
            vehicleId={selectedId}
            variant="modal"
            onClose={onClose}
            selectorSlot={selector}
          />
        )}
      </div>
    </div>
  )
}
