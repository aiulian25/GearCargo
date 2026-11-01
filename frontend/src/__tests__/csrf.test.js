import { it, expect, vi } from 'vitest'
import { createCsrfTransport } from '../utils/csrf'
import { protocolHeaders } from '../utils/mutationProtocol'
import { publicApiRead, cacheablePrivateApi } from '../swPrivateCache'

const origin = 'https://cars.example'
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

it('fetches fresh proof for replay, retries only explicit stale proof, and preserves the intent and body', async () => {
  let tokens = 0
  const sent = []
  const transport = createCsrfTransport(async (request, options) => {
    if (typeof request === 'string') {
      expect(options).toEqual({ credentials: 'same-origin', cache: 'no-store' })
      return json({ csrf_token: `fresh-${++tokens}` })
    }
    sent.push({ headers: Object.fromEntries(request.headers), body: await request.text() })
    return sent.length === 1 ? json({ code: 'CSRF_INVALID' }, 403) : json({ saved: true })
  }, origin)
  const request = new Request(`${origin}/api/vehicles`, { method: 'POST', headers: {
    'X-CSRF-Token': 'never-replay-this', 'Idempotency-Key': 'stable-operation-id', 'If-Match': '"4"',
    'X-GearCargo-Offline-Owner': 'owner-a',
  }, body: '{"name":"Offline draft"}' })
  expect((await transport.fetch(request)).status).toBe(200)
  expect(tokens).toBe(2)
  expect(sent.map(item => item.headers['x-csrf-token'])).toEqual(['fresh-1', 'fresh-2'])
  expect(sent[1]).toEqual({ ...sent[0], headers: { ...sent[0].headers, 'x-csrf-token': 'fresh-2' } })
  expect(protocolHeaders(request.headers)).not.toHaveProperty('X-CSRF-Token')
})

it.each(['CSRF_ORIGIN_REJECTED', 'FORBIDDEN'])('does not retry a %s response', async code => {
  const fetchFn = vi.fn(async request => typeof request === 'string' ? json({ csrf_token: 'fresh' }) : json({ code }, 403))
  expect((await createCsrfTransport(fetchFn, origin).fetch('/api/auth/logout', { method: 'POST' })).status).toBe(403)
  expect(fetchFn).toHaveBeenCalledTimes(2)
})

it('bounds invalid-proof retries and never transmits a mutation if proof cannot be fetched', async () => {
  const rejected = vi.fn(async request => typeof request === 'string' ? json({ csrf_token: 'fresh' }) : json({ code: 'CSRF_INVALID' }, 403))
  expect((await createCsrfTransport(rejected, origin).fetch('/api/auth/logout', { method: 'POST' })).status).toBe(403)
  expect(rejected).toHaveBeenCalledTimes(4)
  const offline = vi.fn(async () => { throw new TypeError('offline') })
  await expect(createCsrfTransport(offline, origin).fetch('/api/vehicles', { method: 'POST' })).rejects.toThrow('offline')
  expect(offline).toHaveBeenCalledTimes(1)
})

it('coalesces concurrent bootstrap reads without retaining tokens for later mutations', async () => {
  let resolve
  const fetchFn = vi.fn(() => new Promise(done => { resolve = done }))
  const transport = createCsrfTransport(fetchFn, origin)
  const a = transport.token(), b = transport.token()
  expect(fetchFn).toHaveBeenCalledTimes(1)
  resolve(json({ csrf_token: 'first' }))
  expect(await Promise.all([a, b])).toEqual(['first', 'first'])
  const c = transport.token()
  expect(fetchFn).toHaveBeenCalledTimes(2)
  resolve(json({ csrf_token: 'second' }))
  expect(await c).toBe('second')
})

it('passes through safe/foreign requests and makes token bootstrap network-only even before login', async () => {
  const fetchFn = vi.fn(async () => json({ ok: true }))
  const transport = createCsrfTransport(fetchFn, origin)
  await transport.fetch('/api/auth/offline-identity')
  await transport.fetch('https://elsewhere.example/api/vehicles', { method: 'POST' })
  expect(fetchFn).toHaveBeenCalledTimes(2)
  for (const [request] of fetchFn.mock.calls) expect(request.headers.has('X-CSRF-Token')).toBe(false)
  const url = new URL('/api/csrf-token', origin)
  expect(publicApiRead(url)).toBe(true)
  expect(cacheablePrivateApi(url)).toBe(false)
})
