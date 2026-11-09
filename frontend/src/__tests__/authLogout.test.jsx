import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

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
  const { isAuthenticated, logout } = useAuth()
  return (
    <>
      <p>{isAuthenticated ? 'signed in' : 'signed out'}</p>
      <button type="button" onClick={() => logout({ sessionEndedByServer: true })}>after account deletion</button>
      <button type="button" onClick={() => logout()}>sign out</button>
    </>
  )
}

const signInThenClick = async (name) => {
  render(<AuthProvider><SignInState /></AuthProvider>)
  await screen.findByText('signed in')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })) })
}

afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: { id: 7 } })
  api.post.mockResolvedValue({ data: {} })
  identity.beginIdentityTransition.mockResolvedValue({ revision: 'signed-out' })
})

describe('logout', () => {
  it('skips the server sign-out once the server ended the session, but still clears this device', async () => {
    await signInThenClick('after account deletion')

    expect(identity.beginIdentityTransition).toHaveBeenCalledWith({ logout: true })
    expect(api.post).not.toHaveBeenCalled()
    expect(identity.forgetBoundIdentity).toHaveBeenCalled()
    expect(screen.getByText('signed out')).toBeTruthy()
  })

  it('asks the server to end the session otherwise', async () => {
    await signInThenClick('sign out')

    expect(identity.beginIdentityTransition).toHaveBeenCalledWith({ logout: true })
    expect(api.post).toHaveBeenCalledWith('/auth/logout')
    expect(screen.getByText('signed out')).toBeTruthy()
  })
})
