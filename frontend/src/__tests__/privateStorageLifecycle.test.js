// @vitest-environment node
import { it, expect, vi } from 'vitest'
import { createPrivateCache, isPrivatePath, publicApiRead, cacheablePrivateApi } from '../swPrivateCache'
import { privateCacheName, OFFLINE_SESSION_MS } from '../utils/privateStorage'

function harness() {
  let state = { revision: 'A', identity: { owner_key: 'owner-a', generation: 'session-a' }, privateUntil: OFFLINE_SESSION_MS }
  const buckets = new Map(), bindings = { tabA: 'A', tabB: 'B' }
  const key = request => typeof request === 'string' ? request : request.url
  const storage = { delete: async name => buckets.delete(name), open: async name => {
    if (!buckets.has(name)) buckets.set(name, new Map())
    const cache = buckets.get(name)
    return { put: async (req, response) => { cache.set(key(req), response.clone()) },
      match: async req => cache.get(key(req))?.clone(), keys: async () => [...cache.keys()].map(url => new Request(url)), delete: async req => cache.delete(key(req)) }
  } }
  const fetchFn = vi.fn(async () => new Response('private A'))
  const expire = vi.fn(async () => { state = { revision: 'closed', identity: null }; buckets.clear() })
  const cache = createPrivateCache({ storage, getState: async () => state, clientRevision: async id => bindings[id], expire, fetchFn, now: () => 1000 })
  const read = (path = '/api/vehicles', clientId = 'tabA', background = false) => cache.handle({ request: new Request(`https://example.test${path}`), event: { clientId }, background })
  return { cache, read, buckets, storage, fetchFn, expire, state: () => state,
    switch: () => { state = { revision: 'B', identity: { owner_key: 'owner-b', generation: 'session-b' }, privateUntil: OFFLINE_SESSION_MS }; buckets.clear() },
    age: () => { state.privateUntil = 999 } }
}
it('public branding and shared reports remain network-only and never enter private caches', () => {
  for (const path of ['/api/config', '/api/reports/shared/token', '/api/reports/shared/token/pdf']) {
    const url = new URL(path, 'https://example.test')
    expect(publicApiRead(url)).toBe(true)
    expect(cacheablePrivateApi(url)).toBe(false)
  }
  expect(publicApiRead(new URL('https://example.test/api/reports/shares'))).toBe(false)
})
it.each(['/uploads/car.jpg?signature=secret', '/media/receipt.jpg', '/api/attachments/1/download'])('classifies %s as private', path => {
  expect(isPrivatePath(new URL(path, 'https://example.test'))).toBe(true)
})
it('keeps private API/media in owner-generation-revision namespaces and supports offline reads', async () => {
  const h = harness()
  await h.read(); await h.read('/uploads/car.jpg')
  expect([...h.buckets.keys()]).toEqual([privateCacheName(h.state(), 'api'), privateCacheName(h.state(), 'media')])
  h.fetchFn.mockRejectedValue(new Error('offline'))
  expect(await (await h.read()).text()).toBe('private A')
  expect((await h.read()).headers.get('Cache-Control')).toBe('no-store')
})
it('blocks stale clients and never gives B the old account cache', async () => {
  const h = harness(); await h.read(); h.switch()
  h.fetchFn.mockRejectedValue(new Error('offline'))
  expect((await h.read()).status).toBe(409)
  await expect(h.read('/api/vehicles', 'tabB')).rejects.toThrow('offline')
})
it('rejects an old response arriving after cleanup without restoring its cache', async () => {
  const h = harness(); let release
  h.fetchFn.mockImplementation(() => new Promise(resolve => { release = resolve }))
  const request = h.read()
  await vi.waitFor(() => expect(release).toBeDefined())
  h.switch(); release(new Response('private A'))
  expect((await request).status).toBe(409)
  expect(h.buckets.size).toBe(0)
})
it('also deletes a cache when the boundary changes during cache.put', async () => {
  const h = harness(), open = h.storage.open
  h.storage.open = async name => {
    const cache = await open(name), put = cache.put
    cache.put = async (...args) => { await put(...args); h.switch() }
    return cache
  }
  expect((await h.read()).status).toBe(409)
  expect(h.buckets.size).toBe(0)
})
it('expires the offline window and never falls back on an explicit session-expired response', async () => {
  const h = harness(); await h.read(); h.age()
  expect((await h.read()).status).toBe(409)
  expect(h.expire).toHaveBeenCalledOnce()
  const other = harness(); await other.read()
  other.fetchFn.mockResolvedValue(Response.json({ code: 'SESSION_EXPIRED' }, { status: 401 }))
  expect((await other.read()).status).toBe(401)
  expect(other.expire).toHaveBeenCalledOnce()
  expect(other.buckets.size).toBe(0)
})
it('a periodic refresh has the same expiry and late-response protection', async () => {
  const h = harness()
  h.fetchFn.mockResolvedValue(new Response('{}', { status: 401 }))
  expect((await h.read('/api/reminders', null, true)).status).toBe(401)
  expect(h.expire).toHaveBeenCalledOnce()
})
it('shares are single-use, scoped, and unavailable after an account change or expiry', async () => {
  const h = harness()
  const share = () => { const data = new FormData(); data.append('receipt', new Blob(['receipt A']), 'receipt.jpg'); return new Request('https://example.test/share-target', { method: 'POST', body: data }) }
  expect(await h.cache.share(share())).toBe(true)
  expect(await (await h.cache.takeShare('tabA')).blob.text()).toBe('receipt A')
  expect(await h.cache.takeShare('tabA')).toBeNull()
  await h.cache.share(share()); h.switch()
  expect(await h.cache.takeShare('tabB')).toBeNull()
  h.age()
  expect(await h.cache.share(share())).toBe(false)
})
