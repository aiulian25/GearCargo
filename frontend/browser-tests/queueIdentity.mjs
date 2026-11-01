/* eslint-disable no-undef */
// Real Chromium + built service worker + Flask cookie-authentication acceptance.
// See docs/OFFLINE_WRITES.md for the isolated fixture and invocation.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'

const root = resolve(process.env.GC_FRONTEND || '.')
const before = process.env.GC_BEFORE_FRONTEND && resolve(process.env.GC_BEFORE_FRONTEND)
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc007/browser')
const mode = process.env.GC_BROWSER_MODE || 'fixed'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
const { build } = require('esbuild')
await mkdir(output, { recursive: true })
for (const [label, source] of [['fixed', root], ['before', before]]) {
  if (!source) continue
  await build({ entryPoints: [join(source, 'browser-tests/queueHarness.jsx')], bundle: true,
    outfile: join(output, `${label}-harness.js`), format: 'esm', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
}

let served = mode === 'before' ? before : root
let servedLabel = mode === 'before' ? 'before' : 'fixed'
let blockWrites = false
const ordinaryWrite = req => req.method !== 'GET' && /^\/api\/(vehicles|fuel|todos)(\/|$)/.test(req.url)
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/api/auth/queue-test') {
      res.setHeader('Content-Type', 'text/html')
      res.setHeader('Cache-Control', 'no-store')
      res.end('<!doctype html><div id="root"></div><script type="module" src="/__gc007-harness.js"></script>')
      return
    }
    if (req.url === '/__gc007-harness.js') {
      res.setHeader('Content-Type', 'application/javascript')
      res.setHeader('Cache-Control', 'no-store')
      res.end(await readFile(join(output, `${servedLabel}-harness.js`)))
      return
    }
    if (req.url.startsWith('/api/') || req.url.startsWith('/__gc007/')) {
      if (blockWrites && ordinaryWrite(req)) { req.socket.destroy(); return }
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: { ...req.headers, 'x-gc007-fixture': 'disposable-browser-only' } }, response => {
        res.writeHead(response.statusCode, response.headers)
        response.pipe(res)
      })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') })
      req.pipe(proxy)
      return
    }
    const path = req.url.split('?')[0]
    const file = join(served, 'dist', path === '/' ? 'index.html' : path)
    const types = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.webmanifest': 'application/manifest+json' }
    res.setHeader('Content-Type', types[extname(file)] || 'application/octet-stream')
    res.setHeader('Cache-Control', 'no-store')
    res.end(await readFile(file))
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const results = []
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn, label) {
  for (let n = 0; n < 450; n++) { if (await fn()) return; await sleep(100) }
  throw new Error(`Timed out: ${label}`)
}
async function pageIn(context, register = true) {
  const page = await context.newPage()
  page.on('pageerror', error => results.push({ browserError: error.message }))
  await page.goto(`${origin}/api/auth/queue-test`)
  await page.waitForFunction(() => window.gc007 && !window.gc007.auth.isLoading)
  if (register) {
    await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
    await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  }
  return page
}
async function login(page, account) {
  await page.evaluate(account => window.gc007.auth.login(`queue-${account.toLowerCase()}@example.invalid`, 'BrowserFixture123!'), account)
  await page.waitForFunction(account => window.gc007.auth.user?.username === `queue_${account}`, account)
}
async function draft(page, name) {
  return page.evaluate(async name => {
    try { await window.gc007.api.post('/vehicles', { name }); return 'saved' }
    catch { return 'failed' }
  }, name)
}
async function rows(page) {
  return page.evaluate(async () => {
    const read = async (name, store) => {
      const db = await new Promise((resolve, reject) => { const r = indexedDB.open(name); r.onsuccess = () => resolve(r.result); r.onerror = reject })
      try {
        if (!db.objectStoreNames.contains(store)) return []
        return await new Promise(resolve => { const r = db.transaction(store).objectStore(store).getAll(); r.onsuccess = () => resolve(r.result) })
      } finally { db.close() }
    }
    const pending = await read('GearCargoMutationIdentity', 'pending')
    const legacy = await read('workbox-background-sync', 'requests')
    return [...pending, ...legacy.map(row => ({ queueName: row.queueName, metadata: row.metadata,
      path: new URL(row.requestData.url).pathname, headers: row.requestData.headers,
      body: row.requestData.body ? new TextDecoder().decode(row.requestData.body) : '' }))]
  })
}
async function identity(page) { return page.evaluate(async () => (await fetch('/api/auth/offline-identity')).json()) }
async function message(page, data) {
  return page.evaluate(data => new Promise((resolve, reject) => {
    const channel = new MessageChannel()
    const timer = setTimeout(() => reject(new Error('Worker acknowledgement timed out')), 20000)
    channel.port1.onmessage = event => { clearTimeout(timer); channel.port1.close(); resolve(event.data) }
    navigator.serviceWorker.controller.postMessage(data, [channel.port2])
  }), data)
}
async function sync(page, queueName = 'gearcargo-account-queue-v1') {
  const cdp = await page.context().newCDPSession(page)
  let registrationId
  cdp.on('ServiceWorker.workerRegistrationUpdated', ({ registrations }) => {
    registrationId = registrations.find(reg => reg.scopeURL === origin + '/')?.registrationId || registrationId
  })
  await cdp.send('ServiceWorker.enable')
  await until(() => registrationId, 'worker registration')
  await cdp.send('ServiceWorker.dispatchSyncEvent', { origin, registrationId, tag: `workbox-background-sync:${queueName}`, lastChance: true })
  await cdp.detach()
}
const records = async () => (await fetch(`${origin}/__gc007/records`)).json()
try {
  // Exact reported path, using the real AuthProvider for offline logout/login.
  const context = await browser.newContext()
  const page = await pageIn(context)
  await login(page, 'A')
  const oldIdentity = mode === 'fixed' ? await identity(page) : null
  const second = mode === 'fixed' ? await pageIn(context) : null
  blockWrites = true
  await context.setOffline(true)
  assert.equal(await draft(page, 'GC007-A-OFFLINE'), 'failed')
  assert((await rows(page)).some(row => row.body.includes('GC007-A-OFFLINE')))
  await page.evaluate(() => window.gc007.auth.logout())
  await context.setOffline(false)
  await login(page, 'B')
  if (second) {
    assert.equal(await draft(second, 'GC007-STALE-TAB'), 'failed')
    blockWrites = false
    const response = await page.evaluate(async scope => {
      const response = await fetch('/api/vehicles', { method: 'POST', headers: {
        'Content-Type': 'application/json', 'X-GearCargo-Offline-Owner': scope.owner_key,
        'X-GearCargo-Offline-Generation': scope.generation }, body: JSON.stringify({ name: 'GC007-COOKIE-RACE' }) })
      return { status: response.status, body: await response.json() }
    }, oldIdentity)
    assert.equal(response.status, 409)
    assert.equal(response.body.code, 'OFFLINE_IDENTITY_MISMATCH')
  }
  blockWrites = false
  await sync(page, mode === 'before' ? 'gearcargo-sync-queue' : undefined)
  await until(async () => (await rows(page)).length === 0, 'cross-account queue drain')
  const afterSwitch = await records()
  results.push({ scenario: 'A offline create, offline logout, B login, reconnect', records: afterSwitch })
  assert(!afterSwitch.B.includes('GC007-A-OFFLINE'), 'B received A\'s queued mutation')
  assert(!afterSwitch.B.includes('GC007-STALE-TAB'))
  assert(!afterSwitch.B.includes('GC007-COOKIE-RACE'))
  let scope = await identity(page)
  let review = await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action: 'export', identity: scope })
  assert.deepEqual(review.entries, [])
  await login(page, 'A')
  scope = await identity(page)
  review = await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action: 'export', identity: scope })
  assert(review.entries.some(entry => entry.body.includes('GC007-A-OFFLINE')))
  assert.equal((await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action: 'discard', identity: scope })).success, true)
  results.push({ scenario: 'stale tab, server cookie race, owner-only export/discard', passed: true })

  // Same-session replay survives a worker restart and token rotation.
  // Hold writes until refresh finishes: a concurrent replay using the revoked
  // access cookie correctly pauses for fresh sign-in under GC-009.
  blockWrites = true
  await context.setOffline(true)
  await draft(page, 'GC007-SAME-ACCOUNT')
  await context.setOffline(false)
  await page.evaluate(() => window.gc007.api.post('/auth/refresh', {}))
  assert.deepEqual(await identity(page), scope)
  blockWrites = false
  const cdp = await context.newCDPSession(page)
  await cdp.send('ServiceWorker.enable')
  await cdp.send('ServiceWorker.stopAllWorkers')
  await cdp.detach()
  await sync(page)
  await until(async () => {
    if ((await records()).A.includes('GC007-SAME-ACCOUNT')) return true
    // Worker termination may leave the existing 20-second lease and network
    // backoff; exercise the supported foreground retry after they expire.
    await message(page, { type: 'FORCE_SYNC', identity: scope })
    await sleep(1000)
    return false
  }, 'same-account replay')
  assert.equal((await records()).A.filter(name => name === 'GC007-SAME-ACCOUNT').length, 1)
  results.push({ scenario: 'same account, token refresh, worker restart', passed: true })

  // Every excluded write fails offline without being persisted.
  await context.setOffline(true)
  for (const path of ['/auth/login', '/auth/password', '/auth/2fa/verify', '/admin/users', '/backup/restore', '/vehicles/1/photo']) {
    await page.evaluate(async path => { try { await window.gc007.api.post(path, { password: 'PRIVATE-GC007-CREDENTIAL', totp_code: 'PRIVATE-GC007-OTP' }) } catch { /* expected offline */ } }, path)
  }
  assert(!(await rows(page)).some(row => row.body.includes('PRIVATE-GC007')))
  await context.setOffline(false)
  results.push({ scenario: 'excluded auth/security/admin/restore/upload bodies', passed: true })
  await context.close()

  // Uninstalling a worker does not erase its queue; a later installation must
  // still refuse to attach it to the next signed-in user.
  const reinstallContext = await browser.newContext()
  let reinstalled = await pageIn(reinstallContext)
  await login(reinstalled, 'A')
  blockWrites = true
  await reinstallContext.setOffline(true)
  await draft(reinstalled, 'GC007-BEFORE-UNINSTALL')
  await reinstalled.evaluate(async () => (await navigator.serviceWorker.getRegistration()).unregister())
  await reinstalled.close()
  await reinstallContext.setOffline(false)
  reinstalled = await pageIn(reinstallContext, false)
  await login(reinstalled, 'B')
  await reinstalled.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
  await reinstalled.waitForFunction(() => !!navigator.serviceWorker.controller)
  await message(reinstalled, { type: 'GET_PENDING_SYNC_COUNT', identity: await identity(reinstalled) })
  blockWrites = false
  await sync(reinstalled)
  assert(!(await records()).B.includes('GC007-BEFORE-UNINSTALL'))
  results.push({ scenario: 'worker uninstall, B login, reinstall', passed: true })
  await reinstallContext.close()

  if (before) {
    served = before; servedLabel = 'before'; blockWrites = true
    const legacyContext = await browser.newContext()
    let legacyPage = await pageIn(legacyContext)
    await login(legacyPage, 'A')
    await legacyContext.setOffline(true)
    await draft(legacyPage, 'GC007-LEGACY-UNKNOWN')
    await legacyPage.evaluate(async () => { try { await window.gc007.api.post('/auth/login', { password: 'PRIVATE-GC007-LEGACY-PASSWORD' }) } catch { /* legacy queues it */ } })
    assert((await rows(legacyPage)).some(row => row.path === '/api/auth/login'))
    await legacyContext.setOffline(false)
    served = root; servedLabel = 'fixed'
    await legacyPage.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      await registration.update()
      if (!registration.waiting) await new Promise(resolve => {
        const installing = registration.installing
        installing.addEventListener('statechange', () => { if (installing.state === 'installed') resolve() })
      })
      registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    })
    await until(async () => (await rows(legacyPage)).length === 0, 'legacy migration')
    await legacyPage.close()
    legacyPage = await pageIn(legacyContext)
    await login(legacyPage, 'B')
    const legacyScope = await identity(legacyPage)
    const status = await message(legacyPage, { type: 'GET_PENDING_SYNC_COUNT', identity: legacyScope })
    assert.equal(status.legacyCount, 2)
    assert.deepEqual((await message(legacyPage, { type: 'REVIEW_OFFLINE_QUEUE', action: 'export', identity: legacyScope })).entries, [])
    const stored = await legacyPage.evaluate(async () => {
      const db = await new Promise(resolve => { const r = indexedDB.open('GearCargoMutationIdentity'); r.onsuccess = () => resolve(r.result) })
      try { return await new Promise(resolve => { const r = db.transaction('quarantine').objectStore('quarantine').getAll(); r.onsuccess = () => resolve(r.result) }) } finally { db.close() }
    })
    assert(!JSON.stringify(stored).includes('PRIVATE-GC007-LEGACY-PASSWORD'))
    blockWrites = false
    await sync(legacyPage)
    assert(!(await records()).B.includes('GC007-LEGACY-UNKNOWN'))
    assert.equal((await message(legacyPage, { type: 'REVIEW_OFFLINE_QUEUE', action: 'discard-legacy', identity: legacyScope })).success, true)
    results.push({ scenario: 'legacy worker upgrade, quarantine, credential-body removal, explicit discard', passed: true })
    await legacyContext.close()
  }

  const deletedContext = await browser.newContext()
  const deletedPage = await pageIn(deletedContext)
  await login(deletedPage, 'A')
  await deletedContext.setOffline(true)
  await draft(deletedPage, 'GC007-DELETED-ACCOUNT')
  assert.equal((await fetch(`${origin}/__gc007/delete-a`, { method: 'POST' })).status, 200)
  await deletedContext.setOffline(false)
  await sync(deletedPage)
  await until(async () => (await rows(deletedPage)).length === 0, 'deleted-owner quarantine')
  await login(deletedPage, 'B')
  assert(!(await records()).B.includes('GC007-DELETED-ACCOUNT'))
  assert.deepEqual((await message(deletedPage, { type: 'REVIEW_OFFLINE_QUEUE', action: 'export', identity: await identity(deletedPage) })).entries, [])
  results.push({ scenario: 'account deletion', passed: true })
  await deletedContext.close()
} finally {
  console.log(JSON.stringify(results, null, 2))
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
