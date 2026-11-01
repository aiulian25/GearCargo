import { it, expect, vi } from 'vitest'
const session = vi.hoisted(() => ({ identity: { owner_id: 1, owner_key: 'a'.repeat(64), generation: 'b'.repeat(64) } }))
vi.mock('../utils/offlineIdentity', () => ({ getBoundIdentity: () => session.identity }))
import { privateNavigationState, readPrivateNavigationState } from '../utils/privateNavigation'

it('keeps receipt prefills out of browser history and forgets them at an identity boundary', () => {
  const privateData = { prefill: { amount: 82, notes: 'Private receipt details' }, attachmentId: 15 }
  const historyState = privateNavigationState(privateData)
  expect(Object.keys(historyState)).toEqual(['privateRef'])
  expect(JSON.stringify(historyState)).not.toContain('Private receipt')
  expect(readPrivateNavigationState(historyState)).toEqual(privateData)
  const original = session.identity
  session.identity = null
  window.dispatchEvent(new Event('offline-identity-changed'))
  session.identity = original
  expect(readPrivateNavigationState(historyState)).toBeNull()
  expect(readPrivateNavigationState(privateData)).toBeNull() // Legacy unscoped history is never imported.
})
