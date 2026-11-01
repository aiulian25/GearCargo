import { getBoundIdentity } from './offlineIdentity'
import { sameIdentity } from './offlinePolicy'

// Receipts/expense prefills must not be serialized into persistent browser
// history, where logout cannot erase older entries. History carries only an
// opaque reference; the original account's mounted app owns the actual data.
const handoffs = new Map()
export function privateNavigationState(value) {
  const identity = getBoundIdentity()
  if (!identity) return null
  const privateRef = crypto.randomUUID()
  handoffs.set(privateRef, { identity, value })
  return { privateRef }
}
export function readPrivateNavigationState(state) {
  const handoff = handoffs.get(state?.privateRef)
  return handoff && sameIdentity(handoff.identity, getBoundIdentity()) ? handoff.value : null
}
if (typeof window !== 'undefined') window.addEventListener('offline-identity-changed', () => {
  for (const [key, handoff] of handoffs) if (!sameIdentity(handoff.identity, getBoundIdentity())) handoffs.delete(key)
})
