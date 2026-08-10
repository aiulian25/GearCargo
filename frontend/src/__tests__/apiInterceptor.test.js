/**
 * Unit tests for the axios response-interceptor auth logic
 * (src/services/api.js `handleAuthError`) — the token-refresh loop from Step 5.
 *
 * All side-effecting dependencies (path, localStorage, toast, redirect, refresh,
 * retry) are injected, so these assert the control flow without a real browser
 * or network: 401 → refresh → retry, single-retry guard, and the
 * session-expired → redirect paths.
 */
import { describe, it, expect, vi } from 'vitest'
import { handleAuthError } from '../services/api'

function makeDeps(overrides = {}) {
  return {
    getPath: () => '/dashboard',            // a normal (non-auth) page
    clearAuth: vi.fn(),
    notifyExpired: vi.fn(),
    redirectSoon: vi.fn(),
    redirectNow: vi.fn(),
    refresh: vi.fn().mockResolvedValue({}),
    retry: vi.fn().mockResolvedValue({ data: 'retried-ok' }),
    ...overrides,
  }
}

const err = (status, data = {}, config = {}) => ({ config, response: { status, data } })

describe('handleAuthError', () => {
  it('401 → refreshes once, retries the original request, and marks it _retry', async () => {
    const deps = makeDeps()
    const error = err(401, {}, {})

    const result = await handleAuthError(error, deps)

    expect(deps.refresh).toHaveBeenCalledTimes(1)
    expect(deps.retry).toHaveBeenCalledWith(error.config)
    expect(result).toEqual({ data: 'retried-ok' })
    expect(error.config._retry).toBe(true)          // prevents an infinite retry loop
    expect(deps.redirectNow).not.toHaveBeenCalled()
    expect(deps.redirectSoon).not.toHaveBeenCalled()
  })

  it('does not retry a request already flagged _retry — rejects, no refresh', async () => {
    const deps = makeDeps()
    const error = err(401, {}, { _retry: true })

    await expect(handleAuthError(error, deps)).rejects.toBe(error)
    expect(deps.refresh).not.toHaveBeenCalled()
    expect(deps.retry).not.toHaveBeenCalled()
  })

  it('SESSION_EXPIRED → clears auth, toasts the backend message, schedules /login, rejects', async () => {
    const deps = makeDeps()
    const error = err(401, { code: 'SESSION_EXPIRED', error: 'Your session has expired.' })

    await expect(handleAuthError(error, deps)).rejects.toBe(error)
    expect(deps.clearAuth).toHaveBeenCalled()
    expect(deps.notifyExpired).toHaveBeenCalledWith('Your session has expired.')
    expect(deps.redirectSoon).toHaveBeenCalledWith('/login')
    expect(deps.refresh).not.toHaveBeenCalled()      // futile to refresh
  })

  it('SESSION_INVALID on an auth page → clears auth but does NOT toast/redirect', async () => {
    const deps = makeDeps({ getPath: () => '/login' })
    const error = err(401, { code: 'SESSION_INVALID' })

    await expect(handleAuthError(error, deps)).rejects.toBe(error)
    expect(deps.clearAuth).toHaveBeenCalled()
    expect(deps.notifyExpired).not.toHaveBeenCalled()
    expect(deps.redirectSoon).not.toHaveBeenCalled()
  })

  it('plain 401 on an auth page → rejects without refreshing', async () => {
    const deps = makeDeps({ getPath: () => '/login' })
    const error = err(401, {}, {})

    await expect(handleAuthError(error, deps)).rejects.toBe(error)
    expect(deps.refresh).not.toHaveBeenCalled()
  })

  it('401 then refresh fails with SESSION_EXPIRED → toast + scheduled /login, no retry', async () => {
    const refreshErr = { response: { data: { code: 'SESSION_EXPIRED', error: 'gone' } } }
    const deps = makeDeps({ refresh: vi.fn().mockRejectedValue(refreshErr) })
    const error = err(401, {}, {})

    await expect(handleAuthError(error, deps)).rejects.toBe(refreshErr)
    expect(deps.retry).not.toHaveBeenCalled()
    expect(deps.notifyExpired).toHaveBeenCalledWith('gone')
    expect(deps.redirectSoon).toHaveBeenCalledWith('/login')
  })

  it('401 then refresh fails for another reason → hard redirect to /login', async () => {
    const refreshErr = { response: { status: 500, data: {} } }
    const deps = makeDeps({ refresh: vi.fn().mockRejectedValue(refreshErr) })
    const error = err(401, {}, {})

    await expect(handleAuthError(error, deps)).rejects.toBe(refreshErr)
    expect(deps.clearAuth).toHaveBeenCalled()
    expect(deps.redirectNow).toHaveBeenCalledWith('/login')
    expect(deps.notifyExpired).not.toHaveBeenCalled()
  })

  it('a non-401 error (e.g. 404) passes straight through, untouched', async () => {
    const deps = makeDeps()
    const error = err(404, {}, {})

    await expect(handleAuthError(error, deps)).rejects.toBe(error)
    expect(deps.refresh).not.toHaveBeenCalled()
    expect(deps.clearAuth).not.toHaveBeenCalled()
    expect(deps.redirectNow).not.toHaveBeenCalled()
  })
})
