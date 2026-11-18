import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'

const SERVER_BUILD = { version: '1.0.0', git_sha: 'abc1234', build_date: '2026-01-01T00:00:00Z' }
const APP_VERSION_ADDRESS = '/api/app-version'

const auth = { isAuthenticated: false }

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../config/build', () => ({
  BUILD: { version: SERVER_BUILD.version, gitSha: SERVER_BUILD.git_sha, buildDate: SERVER_BUILD.build_date },
  IS_PUBLISHED_BUILD: true,
  IS_DEV_BUILD: false,
}))

const { UpdateProvider } = await import('../contexts/UpdateContext')

const requestedAddresses = () => fetch.mock.calls.map(([address]) => address)

describe('update check', () => {
  beforeEach(() => {
    auth.isAuthenticated = false
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => SERVER_BUILD })))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  // Until sign-in is established the service worker refuses the request, so asking earlier loses the check.
  it('asks the server for its version only once the person is signed in', async () => {
    const view = render(<UpdateProvider><span /></UpdateProvider>)
    expect(requestedAddresses()).toEqual([])

    auth.isAuthenticated = true
    view.rerender(<UpdateProvider><span /></UpdateProvider>)

    await waitFor(() => expect(requestedAddresses()).toEqual([APP_VERSION_ADDRESS]))
  })
})
