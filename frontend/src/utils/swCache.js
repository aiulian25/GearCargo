import { getQueueState } from '../db/mutationQueue'
import { purgePrivateStorage } from './privateStorage'

// Compatibility name: callers must suspend identity before clearing storage.
// Cleanup failures propagate; sign-out must never falsely acknowledge a purge.
export async function clearApiCache(revision) {
  const state = await getQueueState()
  if (state.identity) throw new Error('Suspend the private session before clearing its data.')
  await purgePrivateStorage(revision || state.revision)
}
export default clearApiCache
