import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

const OWNER_ID = 7
const WORKER_TOOK_CONTROL = 'controllerchange'

const { api, identity } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
  identity: {
    beginIdentityTransition: vi.fn(), establishOfflineIdentity: vi.fn(), restoreOfflineIdentity: vi.fn(),
    forgetBoundIdentity: vi.fn(), getBoundIdentity: vi.fn(),
  },
}))

vi.mock('../services/api', () => ({ default: api }))
vi.mock('../utils/offlineIdentity', () => identity)
vi.mock('../db/mutationQueue', () => ({ getQueueState: async () => ({ revision: 'signed-in' }) }))
vi.mock('../utils/privateStorage', () => ({
  migratePrivateStorage: async () => {}, readPrivateProfile: async () => null, savePrivateProfile: async () => {},
  privateSessionValid: () => true, clearPrivatePageStorage: () => {},
}))

const { AuthProvider, useAuth } = await import('../contexts/AuthContext')

function SignInState() {
  const { isAuthenticated, isLoading } = useAuth()
  if (isLoading) return <p>checking</p>
  return <p>{isAuthenticated ? 'signed in' : 'signed out'}</p>
}

const workerEvents = new EventTarget()
const workerTakesControl = () => workerEvents.dispatchEvent(new Event(WORKER_TOOK_CONTROL))

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: workerEvents })
  identity.restoreOfflineIdentity.mockResolvedValue(true)
})
afterEach(() => {
  cleanup()
  delete navigator.serviceWorker
})

// On a first visit the worker finishes installing after the person has signed in. Until this page
// tells it which session it belongs to, the worker refuses every request for private data.
describe('a service worker that takes control after sign-in', () => {
  it('is told which session this page belongs to', async () => {
    api.get.mockResolvedValue({ data: { id: OWNER_ID } })
    identity.getBoundIdentity.mockReturnValue({ owner_id: OWNER_ID })
    render(<AuthProvider><SignInState /></AuthProvider>)
    await screen.findByText('signed in')

    workerTakesControl()

    expect(identity.restoreOfflineIdentity).toHaveBeenCalledWith(OWNER_ID)
  })

  it('is told nothing while nobody is signed in', async () => {
    api.get.mockRejectedValue({ response: { status: 401 } })
    identity.getBoundIdentity.mockReturnValue(null)
    render(<AuthProvider><SignInState /></AuthProvider>)
    await screen.findByText('signed out')

    workerTakesControl()

    expect(identity.restoreOfflineIdentity).not.toHaveBeenCalled()
  })
})
