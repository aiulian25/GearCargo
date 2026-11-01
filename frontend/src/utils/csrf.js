// Proof lives only in memory while a request is being prepared. Never persist
// it in IndexedDB, a queued Request, localStorage, or the worker's caches.
export const needsCsrf = method => !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())

export function createCsrfTransport(fetchFn = (...args) => fetch(...args), origin = globalThis.location?.origin) {
  let pending
  // The auth alias is network-only even in the previous deployed worker.
  const token = () => {
    if (!pending) pending = (async () => {
      const response = await fetchFn(new URL('/api/auth/csrf-token', origin).href, { credentials: 'same-origin', cache: 'no-store' })
      if (!response.ok) throw Object.assign(new Error('Could not verify this request. Reload and try again.'), { status: response.status })
      const data = await response.json()
      if (!data.csrf_token) throw new Error('Request verification token is unavailable.')
      return data.csrf_token
    })().finally(() => { pending = null })
    return pending
  }
  return {
    token,
    fetch: async (input, options) => {
      const request = new Request(typeof input === 'string' ? new URL(input, origin) : input, options)
      const url = new URL(request.url)
      if (url.origin !== origin || !url.pathname.startsWith('/api/') || !needsCsrf(request.method)) return fetchFn(request)
      const send = async () => {
        const headers = new Headers(request.headers)
        headers.set('X-CSRF-Token', await token())
        return fetchFn(new Request(request.clone(), { headers }))
      }
      const response = await send()
      // The boundary rejects before any mutation. Refresh proof once without
      // changing the request body, owner, revision, or idempotency key.
      if (response.status === 403 && (await response.clone().json().catch(() => ({}))).code === 'CSRF_INVALID') return send()
      return response
    },
  }
}

const browserCsrf = createCsrfTransport()
export const getCsrfToken = () => browserCsrf.token()
