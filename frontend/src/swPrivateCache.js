import { PRIVATE_CACHE_PREFIX, privateCacheName, privateSessionValid } from './utils/privateStorage'

export const isPrivatePath = url => /^\/(api|media|uploads)(\/|$)/.test(url.pathname)
export const publicApiRead = url => ['/api/config', '/api/csrf-token'].includes(url.pathname) || url.pathname.startsWith('/api/reports/shared/')
export const cacheablePrivateApi = url => url.pathname.startsWith('/api/') && !/^\/api\/reconciliation(?:\/|$)/.test(url.pathname) && !publicApiRead(url) && !['/api/auth/', '/api/admin/', '/api/csrf-token', '/api/backup/', '/api/push/'].some(prefix => url.pathname.startsWith(prefix))
const unavailable = () => Response.json({ code: 'PRIVATE_SESSION_UNAVAILABLE', error: 'Sign in online to unlock private data.' }, { status: 409, headers: { 'Cache-Control': 'no-store' } })
export const noStore = response => {
  const headers = new Headers(response.headers)
  headers.set('Cache-Control', 'no-store')
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers })
}

// Unique generation/revision namespaces plus checks before AND after put prevent
// a late old response from repopulating the next account's cache after a purge.
export function createPrivateCache({ storage, getState, clientRevision, expire, fetchFn = fetch, now = Date.now }) {
  const current = async scope => { const state = await getState(); return privateSessionValid(state, now()) && state.revision === scope.revision }
  async function scopeFor(clientId, background) {
    const state = await getState()
    if (!privateSessionValid(state, now())) {
      if (state.identity) await expire(state.revision)
      return null
    }
    if (!background && (!clientId || await clientRevision(clientId) !== state.revision)) return null
    return state
  }
  async function put(scope, kind, key, response) {
    const name = privateCacheName(scope, kind)
    if (!(await current(scope))) return false
    const cache = await storage.open(name)
    await cache.put(key, response)
    if (!(await current(scope))) { await storage.delete(name); return false }
    const keys = await cache.keys()
    for (const old of keys.slice(0, Math.max(0, keys.length - 100))) await cache.delete(old)
    return true
  }
  return {
    handle: async ({ request, event, background = false }) => {
      const scope = await scopeFor(event?.clientId, background)
      if (!scope) return unavailable()
      const url = new URL(request.url), kind = url.pathname.startsWith('/api/') && request.destination !== 'image' ? 'api' : 'media'
      const allowed = kind === 'media' || cacheablePrivateApi(url)
      const name = privateCacheName(scope, kind)
      const cached = async () => {
        if (!allowed || !(await current(scope))) return null
        const response = await (await storage.open(name)).match(request)
        return await current(scope) ? response : null
      }
      if (kind === 'media') { const hit = await cached(); if (hit) return hit }
      try {
        const response = await fetchFn(new Request(request, { cache: 'no-store' }))
        if (!(await current(scope))) return unavailable()
        // Never mask authentication failures with an old successful response.
        if (response.status === 401) {
          const data = await response.clone().json().catch(() => ({}))
          if (background || ['SESSION_EXPIRED', 'SESSION_INVALID'].includes(data.code)) await expire(scope.revision)
          return noStore(response)
        }
        if (allowed && response.ok && !(await put(scope, kind, request, noStore(response.clone())))) return unavailable()
        return await current(scope) ? noStore(response) : unavailable()
      } catch (error) {
        const hit = await cached()
        if (hit) return hit
        throw error
      }
    },
    share: async (request, clientId) => {
      const scope = await scopeFor(clientId, true)
      if (!scope) return false // Never hand an anonymous receipt to the next login.
      const data = await request.formData(), file = data.get('receipt')
      if (!file || typeof file === 'string' || !file.size || file.size > 10 * 1024 * 1024) return false
      return put(scope, 'share', new URL('/__shared_receipt', request.url).href, new Response(file, { headers: {
        'Content-Type': file.type || 'application/octet-stream', 'X-Shared-Filename': encodeURIComponent(file.name || 'receipt.jpg'),
      } }))
    },
    takeShare: async (clientId) => {
      const scope = await scopeFor(clientId)
      if (!scope) return null
      const cache = await storage.open(privateCacheName(scope, 'share'))
      const keys = await cache.keys()
      const response = keys[0] && await cache.match(keys[0])
      await storage.delete(privateCacheName(scope, 'share'))
      if (!response) return null
      const blob = await response.blob()
      return await current(scope) ? { blob, name: decodeURIComponent(response.headers.get('X-Shared-Filename') || 'receipt.jpg') } : null
    },
  }
}
export { PRIVATE_CACHE_PREFIX }
