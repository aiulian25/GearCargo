import { afterEach, it, expect, vi } from 'vitest'
import axios from 'axios'
import api from '../services/api'
import { getCsrfToken } from '../utils/csrf'
vi.mock('../utils/csrf', async importOriginal => ({ ...(await importOriginal()), getCsrfToken: vi.fn(async () => 'test-proof') }))

const boundary = vi.hoisted(() => ({ revision: 'test-session' }))
vi.mock('../db/mutationQueue', () => ({ getQueueState: async () => ({ revision: boundary.revision }) }))

vi.mock('../utils/offlineIdentity', () => ({
  getBoundIdentity: () => ({ owner_id: 1, owner_key: 'a'.repeat(64), generation: 'b'.repeat(64) }),
  requireCurrentIdentity: vi.fn(async () => {}),
  beginIdentityTransition: vi.fn(async () => {}),
}))
afterEach(() => { vi.restoreAllMocks(); boundary.revision = 'test-session' })

it('keeps the operation ID and revision on an automatic token-refresh retry', async () => {
  vi.spyOn(axios, 'post').mockResolvedValue({ status: 200 })
  const attempts = []
  const adapter = async config => {
    attempts.push(config.headers.toJSON())
    if (attempts.length === 1) throw { config, response: { status: 401, data: {} } }
    return { config, status: 200, data: { saved: true }, headers: {} }
  }
  const response = await api.put('/fuel/1', { notes: 'Draft' }, { adapter, headers: { 'if-match': '"123"' } })
  expect(response.data.saved).toBe(true)
  expect(attempts).toHaveLength(2)
  expect(attempts[1]).toEqual(attempts[0])
  expect(attempts[0]['Idempotency-Key']).toMatch(/^[a-f0-9-]{36}$/)
  expect(attempts[0]['if-match']).toBe('"123"')
})

it('honors explicitly supplied keys regardless of header case', async () => {
  let sent
  const key = 'same-intent-lowercase-header'
  await api.post('/fuel', {}, { headers: { 'idempotency-key': key }, adapter: async config => {
    sent = config.headers.get('Idempotency-Key')
    return { config, status: 201, data: {}, headers: {} }
  } })
  expect(sent).toBe(key)
})

it('blocks a versionless edit before transport and never treats it as an offline save', async () => {
  const adapter = vi.fn()
  await expect(api.put('/fuel/1', { notes: 'Draft' }, { adapter })).rejects.toMatchObject({ response: { status: 428 } })
  expect(adapter).not.toHaveBeenCalled()
})


it('accepts a durable queue acknowledgement without pretending the server saved it', async () => {
  const { isOfflineWriteError } = await import('../utils/offlineWrite')
  const adapter = async config => ({ config, status: 202, data: { code: 'OFFLINE_QUEUED' }, headers: { 'x-gearcargo-queued': '1' } })
  let error
  try { await api.post('/fuel', {}, { adapter }) } catch (failure) { error = failure }
  expect(isOfflineWriteError(error)).toBe(true)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  expect(isOfflineWriteError(new Error('network or storage failed'))).toBe(false)
})

it.each([200, 401])('ignores a late HTTP %s response from an earlier identity without refreshing or clearing the new one', async status => {
  const refresh = vi.spyOn(axios, 'post')
  const adapter = async config => {
    boundary.revision = 'new-session'
    if (status === 401) throw { config, response: { status, data: { code: 'SESSION_EXPIRED' } } }
    return { config, status, data: { private: 'old profile' }, headers: {} }
  }
  await expect(api.get('/auth/me', { adapter })).rejects.toThrow('Sign-in changed')
  expect(refresh).not.toHaveBeenCalled()
})

it('refreshes stale CSRF proof once without changing the operation ID or revision', async () => {
  getCsrfToken.mockResolvedValueOnce('stale').mockResolvedValueOnce('fresh')
  const sent = []
  const adapter = async config => {
    sent.push(config.headers.toJSON())
    if (sent.length === 1) throw { config, response: { status: 403, data: { code: 'CSRF_INVALID' } } }
    return { config, status: 201, data: {}, headers: {} }
  }
  await api.put('/fuel/1', { notes: 'Keep draft' }, { adapter, headers: { 'If-Match': '"7"' } })
  expect(sent).toHaveLength(2)
  expect(sent[1]).toEqual({ ...sent[0], 'X-CSRF-Token': 'fresh' })
})

it('lets eligible writes reach the offline worker when token bootstrap has a network failure', async () => {
  getCsrfToken.mockRejectedValueOnce(new TypeError('offline'))
  const adapter = vi.fn(async config => ({ config, status: 202, data: { code: 'OFFLINE_QUEUED' }, headers: { 'x-gearcargo-queued': '1' } }))
  await expect(api.post('/vehicles', { name: 'Offline' }, { adapter })).rejects.toMatchObject({ code: 'OFFLINE_QUEUED' })
  expect(adapter).toHaveBeenCalledTimes(1)
  expect(adapter.mock.calls[0][0].headers.has('X-CSRF-Token')).toBe(false)
})

it('blocks transport if sign-in changes while obtaining proof', async () => {
  getCsrfToken.mockImplementationOnce(async () => { boundary.revision = 'another-session'; return 'fresh' })
  const adapter = vi.fn()
  await expect(api.post('/auth/logout', {}, { adapter })).rejects.toThrow('Sign-in changed')
  expect(adapter).not.toHaveBeenCalled()
})
