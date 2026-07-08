import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { vehicleApi, configApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import { useAuth } from '../../contexts/AuthContext'
import { ASSISTANT_NAME, APP_NAME, APP_LOGO_SRC } from '../../config/brand'

const Icons = {
  back: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
    </svg>
  ),
  send: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  ),
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
}

// The assistant avatar (app logo). Decorative beside each bubble — the bubble
// text carries the content, so screen readers don't need it repeated.
function AssistantAvatar({ decorative = true, name = ASSISTANT_NAME }) {
  return (
    <img
      src={APP_LOGO_SRC}
      alt={decorative ? '' : name}
      aria-hidden={decorative ? 'true' : undefined}
      width={28}
      height={28}
      className="w-7 h-7 rounded-lg shrink-0 object-cover bg-[var(--color-bg-secondary)]"
    />
  )
}

// Rotating pool of on-topic starter questions. We show a rotating subset each
// time the chat mounts so a fresh conversation doesn't always open with the
// same three prompts.
const SUGGESTION_KEYS = [
  ['chat.suggestService', 'When is my next service due?'],
  ['chat.suggestFuelYear', 'How much did I spend on fuel last year?'],
  ['chat.suggestTotal', 'What have I spent on this vehicle in total?'],
  ['chat.suggestReminders', 'What reminders are coming up?'],
  ['chat.suggestInsurance', 'When does my insurance expire?'],
  ['chat.suggestConsumables', 'When did I last change the filters?'],
  ['chat.suggestEfficiency', 'What is my average fuel consumption?'],
]
const SUGGESTIONS_SHOWN = 3

/**
 * Reusable AI assistant chat. Hosts the full conversation (branded greeting,
 * rotating suggestion chips, per-vehicle Q&A via vehicleApi.chat) and is used
 * both full-page (VehicleChat) and inside the dashboard ChatModal.
 *
 * Props:
 *   vehicleId    – the vehicle to chat about (chat is per-vehicle server-side)
 *   variant      – 'page' | 'modal' (affects the header + container sizing)
 *   onBack       – page variant: back handler for the ← button
 *   onClose      – modal variant: close handler for the × button
 *   selectorSlot – modal variant: optional node (e.g. a vehicle <select>) shown
 *                  in the header when the user has more than one vehicle
 */
export default function AssistantChat({ vehicleId, fleet = false, fleetLabel = '', variant = 'page', onBack, onClose, selectorSlot = null }) {
  const { t, language } = useTranslation()
  const { user } = useAuth()

  const [vehicle, setVehicle] = useState(null)
  const [messages, setMessages] = useState([]) // { role: 'user'|'assistant'|'error', text }
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [online, setOnline] = useState(navigator.onLine)
  // Assistant + app name from the backend (white-label safe); fall back to the
  // build-time brand defaults so the greeting works instantly + offline.
  const [assistantName, setAssistantName] = useState(ASSISTANT_NAME)
  const [appName, setAppName] = useState(APP_NAME)
  const listRef = useRef(null)

  // Switching the vehicle (modal selector) starts a fresh conversation so the
  // greeting re-seeds and no answers carry across vehicles.
  useEffect(() => {
    setMessages([])
    setInput('')
    setVehicle(null)
    // Fleet mode has no single vehicle — use a synthetic marker so the greeting
    // effect can seed a fleet-wide welcome without fetching a vehicle.
    if (fleet) {
      setVehicle({ fleet: true, name: fleetLabel })
      return
    }
    if (vehicleId == null) return
    vehicleApi.getById(vehicleId).then((r) => setVehicle(r.data)).catch(() => {})
  }, [vehicleId, fleet, fleetLabel])

  // Sync the assistant/app name with the backend persona (CHAT_ASSISTANT_NAME).
  useEffect(() => {
    configApi.get()
      .then((r) => {
        if (r.data?.assistant_name) setAssistantName(r.data.assistant_name)
        if (r.data?.app_name) setAppName(r.data.app_name)
      })
      .catch(() => {})
  }, [])

  // Whether the user has sent anything yet (controls greeting re-seed + suggestions).
  const hasUserMessage = messages.some((m) => m.role === 'user')
  // After a guardrail refusal, re-surface the suggestion chips to redirect the
  // user back to on-topic questions.
  const lastMessage = messages[messages.length - 1]
  const lastWasRefusal = lastMessage?.role === 'assistant' && !!lastMessage?.refused

  // Seed the branded greeting as a UI-only assistant message: it is never sent
  // to the model, shows instantly, and carries the logo avatar. Re-seeds on
  // language/name/vehicle change while the conversation hasn't started.
  useEffect(() => {
    if (!vehicle || hasUserMessage) return
    const firstName = (user?.name || '').trim().split(/\s+/)[0]
    const base = { assistant: assistantName, app: appName, name: firstName }

    let greeting
    if (fleet) {
      // Fleet-wide welcome (spans all vehicles).
      greeting = t('chat.greetingFleet', base)
        || `Hi! Ask me anything across all your vehicles — compare costs, totals, and more.`
    } else {
      const vehicleDesc = [vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ').trim()
      if (firstName && vehicleDesc) {
        greeting = t('chat.greetingWithVehicle', { ...base, vehicle: vehicleDesc })
      } else if (firstName) {
        greeting = t('chat.greeting', base)
      } else {
        greeting = t('chat.greetingGeneric', base)
      }
    }
    setMessages([{ role: 'assistant', text: greeting, greeting: true }])
  }, [vehicle, language, user, hasUserMessage, assistantName, appName, fleet, t])

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])

  // Auto-scroll to the latest message.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  const errorTextForCode = useCallback((code, status) => {
    if (status === 429) return t('chat.rateLimited') || 'Too many questions. Please wait a moment and try again.'
    if (code === 'ai_disabled' || code === 'ai_not_configured') return t('chat.aiNotConfigured') || 'The AI assistant is not available on this server.'
    if (code === 'ai_no_answer') return t('chat.noAnswer') || "I couldn't work out an answer to that. Try rephrasing, or ask about your fuel, services, costs or reminders."
    if (code === 'ai_timeout') return t('chat.aiTimeout') || 'The assistant took too long to respond. Please try again in a moment.'
    return t('chat.aiUnavailable') || "I couldn't reach the AI service just now. Please try again shortly."
  }, [t])

  const send = useCallback(async (text) => {
    const question = (text ?? input).trim()
    if (!question || loading || (!fleet && vehicleId == null)) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setLoading(true)
    try {
      const res = fleet
        ? await vehicleApi.chatFleet(question, language)
        : await vehicleApi.chat(vehicleId, question, language)
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: res.data?.answer || '',
        refused: !!res.data?.refused,
      }])
    } catch (err) {
      const code = err.response?.data?.code
      setMessages((prev) => [...prev, { role: 'error', text: errorTextForCode(code, err.response?.status) }])
    } finally {
      setLoading(false)
    }
  }, [vehicleId, fleet, input, language, loading, errorTextForCode])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // Rotate the starter suggestions: pick SUGGESTIONS_SHOWN from a random offset
  // in the pool, re-rolled whenever this chat (re)mounts or the vehicle changes.
  const suggestions = useMemo(() => {
    const start = Math.floor(Math.random() * SUGGESTION_KEYS.length)
    return Array.from({ length: SUGGESTIONS_SHOWN }, (_, i) => {
      const [key, fallback] = SUGGESTION_KEYS[(start + i) % SUGGESTION_KEYS.length]
      return t(key) || fallback
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vehicleId, fleet, language])

  const isModal = variant === 'modal'

  return (
    <div className={isModal ? 'flex flex-col h-full' : 'flex flex-col min-h-[calc(100vh-3.5rem)] max-w-2xl mx-auto'}>
      {/* Header */}
      <div className="sticky top-0 z-10 bg-[var(--color-bg-primary)] border-b border-[var(--color-border)] px-4 py-3 flex items-center gap-3">
        {!isModal && (
          <button onClick={onBack} className="btn-icon shrink-0" aria-label={t('common.back') || 'Back'}>
            {Icons.back}
          </button>
        )}
        <AssistantAvatar decorative={false} name={assistantName} />
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold truncate">{assistantName}</h1>
          {selectorSlot || (
            <p className="text-2xs text-[var(--color-text-muted)] truncate">
              {vehicle ? vehicle.name : (t('chat.title') || 'Vehicle Assistant')}
            </p>
          )}
        </div>
        {isModal && (
          <button onClick={onClose} className="btn-icon shrink-0" aria-label={t('common.close') || 'Close'}>
            {Icons.close}
          </button>
        )}
      </div>

      {/* Messages */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3" role="log" aria-live="polite" aria-label={t('chat.title') || 'Vehicle Assistant'}>
        {messages.map((m, i) => {
          const isUser = m.role === 'user'
          const isAssistant = m.role === 'assistant'
          const text = isAssistant && m.refused ? (t('chat.refusal') || m.text) : m.text
          const showAvatar = isAssistant || m.role === 'error'
          return (
            <div key={i} className={`flex items-end gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
              {showAvatar && <AssistantAvatar decorative={false} name={assistantName} />}
              <div
                className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm whitespace-pre-wrap break-words leading-relaxed ${
                  isUser
                    ? 'bg-[var(--color-accent)] text-white rounded-br-md'
                    : m.role === 'error'
                      ? 'bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20 rounded-bl-md'
                      : m.refused
                        ? 'bg-[var(--color-bg-secondary)] text-[var(--color-text-muted)] italic rounded-bl-md'
                        : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)] rounded-bl-md'
                }`}
              >
                {text}
              </div>
            </div>
          )
        })}

        {/* Suggestion chips — shown under the greeting until the first question,
            and again after a refusal to redirect the user to on-topic questions. */}
        {!loading && (!hasUserMessage || lastWasRefusal) && (
          <div className="flex flex-col gap-2 items-stretch max-w-sm mx-auto pt-1">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => send(s)}
                disabled={loading || !online}
                className="text-sm px-3 py-2 rounded-xl bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] text-left disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <div className="flex items-end gap-2 justify-start" aria-live="polite">
            <AssistantAvatar />
            <div className="bg-[var(--color-bg-secondary)] px-4 py-3 rounded-2xl rounded-bl-md" aria-label={t('chat.thinking') || 'Thinking…'}>
              <span className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 rounded-full bg-[var(--color-text-muted)] animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="sticky bottom-0 bg-[var(--color-bg-primary)] border-t border-[var(--color-border)] px-4 py-3">
        {!online && (
          <p className="text-2xs text-[var(--color-text-muted)] text-center mb-2">{t('chat.offline') || 'You are offline — the assistant needs a connection.'}</p>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send() }} className="flex items-end gap-2">
          <label htmlFor="chat-input" className="sr-only">{t('chat.inputLabel') || 'Ask a question'}</label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={500}
            disabled={loading || !online}
            placeholder={fleet
              ? (t('chat.fleetHint') || 'Ask across all your vehicles…')
              : (t('chat.placeholder') || 'Ask about this vehicle…')}
            className="input flex-1 resize-none max-h-32 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !online || !input.trim()}
            className="btn-primary shrink-0 !px-3"
            aria-label={t('chat.send') || 'Send'}
          >
            {Icons.send}
          </button>
        </form>
        <p className="text-2xs text-[var(--color-text-muted)] text-center mt-2 leading-relaxed">
          {t('chat.disclaimer') || 'AI answers are based on your data and may be inaccurate.'}
        </p>
      </div>
    </div>
  )
}
