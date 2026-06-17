/**
 * Brand / assistant identity — single source of truth (CHAT_HARDENING_PLAN §13.2).
 *
 * Keeping the assistant name in ONE place prevents drift between the chat
 * greeting, avatar alt text and (future) backend system prompt. The name
 * defaults to the app name for brand consistency and white-label safety.
 *
 * White-label / follow-up: when the backend exposes `CHAT_ASSISTANT_NAME`
 * (CHAT_HARDENING_PLAN §1 / Layer 1), wire it through here so the UI greeting
 * and the model's system-prompt persona always use the same name.
 */

export const APP_NAME = 'GearCargo'

// The conversational agent's name. Defaults to the app name.
export const ASSISTANT_NAME = APP_NAME

// App logo used as the assistant avatar in the chat. 192px is crisp at the
// small sizes we render it (≤32px) on high-DPI screens.
export const APP_LOGO_SRC = '/icons/logo-192.png'
