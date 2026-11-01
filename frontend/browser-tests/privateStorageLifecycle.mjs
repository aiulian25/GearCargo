/* eslint-disable no-undef */
// Real Chromium + built service worker + Flask cookie-authentication acceptance.
// See docs/PRIVATE_BROWSER_DATA.md for the isolated fixture and invocation.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'

const root = resolve(process.env.GC_FRONTEND || '.')
const before = process.env.GC_BEFORE_FRONTEND && resolve(process.env.GC_BEFORE_FRONTEND)
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc011/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
const { build } = require('esbuild')
await mkdir(output, { recursive: true })
for (const [label, source] of [['fixed', root], ['before', before]]) {
  if (!source) continue
  await build({ entryPoints: [join(source, 'browser-tests/privateStorageHarness.jsx')], bundle: true,
    outfile: join(output, `${label}-harness.js`), format: 'esm', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
}

let lateResponse, lateSeen = false
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/api/auth/private-test') {
      res.setHeader('Content-Type', 'text/html'); res.setHeader('Cache-Control', 'no-store')
      res.end('<!doctype html><div id="root"></div><script type="module" src="/__gc011-harness.js"></script>'); return
    }
    if (req.url === '/__gc011-harness.js') {
      res.setHeader('Content-Type', 'application/javascript'); res.setHeader('Cache-Control', 'no-store')
      res.end(await readFile(join(output, 'fixed-harness.js'))); return
    }
    if (req.url.startsWith('/uploads/') || req.url.startsWith('/media/')) {
      res.setHeader('Content-Type', 'image/svg+xml'); res.end('<svg xmlns="http://www.w3.org/2000/svg" width="5" height="5"><text>PRIVATE-PHOTO-A</text></svg>'); return
    }
    if (req.url.includes('gc011=expire')) {
      res.writeHead(401, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ code: 'SESSION_EXPIRED', error: 'Expired test session' })); return
    }
    if (req.url.startsWith('/api/') || req.url.startsWith('/__gc007/')) {
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method, path: req.url,
        headers: { ...req.headers, 'x-gc007-fixture': 'disposable-browser-only' } }, response => {
        if (req.url.includes('gc011=late')) {
          const chunks = []; response.on('data', c => chunks.push(c)); response.on('end', () => {
            lateResponse = () => { res.writeHead(response.statusCode, response.headers); res.end(Buffer.concat(chunks)) }; lateSeen = true
          }); return
        }
        res.writeHead(response.statusCode, response.headers); response.pipe(res)
      })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') }); req.pipe(proxy); return
    }
    const path = req.url.split('?')[0]
    const file = join(root, 'dist', path === '/' ? 'index.html' : path)
    const types = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.webmanifest': 'application/manifest+json' }
    res.setHeader('Content-Type', types[extname(file)] || 'application/octet-stream'); res.setHeader('Cache-Control', 'no-store')
    res.end(await readFile(file))
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const results = []
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn, label) { for (let n = 0; n < 200; n++) { if (await fn()) return; await pause(100) } throw new Error(`Timed out: ${label}`) }
async function harness(context) {
  const page = await context.newPage()
  page.on('pageerror', error => results.push({ browserError: error.message }))
  await page.goto(`${origin}/api/auth/private-test`)
  await page.waitForFunction(() => window.gc011 && !window.gc011.auth.isLoading)
  await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  return page
}
async function login(page, account) {
  await page.evaluate(account => window.gc011.auth.login(`queue-${account.toLowerCase()}@example.invalid`, 'BrowserFixture123!'), account)
  await page.waitForFunction(account => window.gc011.auth.user?.username === `queue_${account}`, account)
}
async function inventory(page) {
  return page.evaluate(async () => ({ caches: await caches.keys(), settings: await gc011.db.settings.toArray(),
    privateLocal: ['auth_session', 'userEmail', 'username', 'gearcargo_user_location'].filter(key => localStorage.getItem(key)),
    state: await gc011.mutationDb.state.toArray(), pending: await gc011.mutationDb.pending.toArray(),
    held: await gc011.mutationDb.quarantine.toArray(), receipts: (await gc011.mutationDb.receipts.toArray()).map(row => ({ ...row, blob: !!row.blob })) }))
}
function assertPurged(data) {
  assert(!data.caches.some(name => name.startsWith('gearcargo-private-') || ['images', 'api-cache', 'media-cache', 'share-target-cache'].includes(name)))
  assert(!data.settings.some(row => row.key === 'user'))
  assert.equal(data.privateLocal.length, 0)
  assert(!data.state.some(row => row.key === 'private-profile' || row.key.startsWith('private-client:')))
  assert(data.caches.some(name => name.includes('precache')), 'App shell remains cached')
}
async function warm(page) {
  await page.evaluate(async () => {
    await gc011.api.get('/vehicles')
    await fetch('/uploads/car.svg?signature=private-A'); await fetch('/media/receipt.svg')
    const image = new Image(); image.src = '/uploads/car.svg?signature=image-A'; document.body.append(image)
    await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject })
  })
}
async function share(page) {
  return page.evaluate(async () => { const body = new FormData(); body.append('receipt', new File(['original share A'], 'share.jpg', { type: 'image/jpeg' })); const result = await fetch('/share-target', { method: 'POST', body }); return result.url })
}
try {
  const context = await browser.newContext()
  // Migration must remove old unscoped receipts and images before any login.
  const seed = await context.newPage(); await seed.goto(`${origin}/offline.html`)
  await seed.evaluate(async () => {
    for (const name of ['images', 'api-cache', 'media-cache', 'share-target-cache']) await (await caches.open(name)).put('/legacy-private', new Response('private legacy'))
    await new Promise((resolve, reject) => { const req = indexedDB.open('GearCargoDB', 30); req.onupgradeneeded = () => req.result.createObjectStore('settings', { keyPath: 'key' }); req.onsuccess = () => {
      const db = req.result, tx = db.transaction('settings', 'readwrite'); tx.objectStore('settings').put({ key: 'user', value: { id: 1, username: 'legacy private' } }); tx.oncomplete = () => { db.close(); resolve() }
    }; req.onerror = reject })
  })
  const page = await harness(context); await seed.close()
  assertPurged(await inventory(page))
  assert.equal(await page.evaluate(async () => (await fetch('/api/config')).status), 200)
  assert.equal(await page.evaluate(async () => (await fetch('/api/reports/shared/invalid-fixture-token')).status), 404)
  results.push({ scenario: 'Upgrade removes unscoped API/media/images/share caches and cached profile; app assets remain', passed: true })

  const sharedBeforeLogin = await share(page)
  assert(sharedBeforeLogin.endsWith('/login?share=sign-in-required'))
  await login(page, 'A')
  assert.equal(await page.evaluate(async () => (await gc011.workerMessage('TAKE_SHARED_RECEIPT')).receipt), null)
  results.push({ scenario: 'Receipt shared before login is discarded and cannot reach the next account', passed: true })

  const vehicle = await page.evaluate(async () => (await gc011.api.post('/vehicles', { name: 'GC011 Offline Vehicle' })).data.vehicle)
  await warm(page)
  let data = await inventory(page)
  assert(data.caches.some(name => name.endsWith('-media') && name.startsWith('gearcargo-private-')))
  assert(!data.caches.includes('images'))
  await share(page)
  const original = await page.evaluate(async () => { const result = await gc011.workerMessage('TAKE_SHARED_RECEIPT'); return result.receipt?.blob.text() })
  assert.equal(original, 'original share A')
  assert.equal(await page.evaluate(async () => (await gc011.workerMessage('TAKE_SHARED_RECEIPT')).receipt), null)
  results.push({ scenario: 'Signed uploads use private caches; same-owner shared receipt is read once', passed: true })

  // Real production app shell, not the harness, must restore the scoped offline profile.
  await context.setOffline(true)
  const offlinePage = await context.newPage(); offlinePage.on('console', message => console.log('Offline console:', message.text())); offlinePage.on('pageerror', error => console.log('Offline page error:', error.message)); await offlinePage.goto(`${origin}/vehicles`)
  try { await offlinePage.getByText('GC011 Offline Vehicle', { exact: true }).waitFor({ timeout: 15000 }) } catch (error) { console.log('Offline URL/body/online', offlinePage.url(), await offlinePage.locator('body').innerText(), await offlinePage.evaluate(() => navigator.onLine)); console.log('Storage', JSON.stringify(await inventory(page))); throw error }
  await offlinePage.close()
  await page.evaluate(async vehicleId => gc011.saveExpenseWithReceipt({ resource: 'fuel', payload: { vehicle_id: vehicleId, date: '2026-10-31', liters: 5, total_cost: 10, odometer: 10 }, config: gc011.mutationOptions(), file: new File(['%PDF original pending'], 'pending.pdf', { type: 'application/pdf' }) }), vehicle.id)
  await page.evaluate(() => gc011.auth.logout())
  data = await inventory(page); assertPurged(data)
  assert.equal(data.pending.length, 0); assert.equal(data.held.length, 1); assert.equal(data.receipts.length, 1); assert(data.receipts[0].blob)
  assert.equal(data.receipts[0].status, 'identity_changed')
  const signedOutOffline = await context.newPage(); await signedOutOffline.goto(`${origin}/vehicles`)
  await signedOutOffline.waitForURL('**/login', { timeout: 15000 }); await signedOutOffline.close()
  await context.setOffline(false)
  await login(page, 'B')
  assert.deepEqual(await page.evaluate(async () => (await gc011.workerMessage('REVIEW_RECEIPTS', { identity: gc011.getBoundIdentity(), action: { type: 'list' } })).entries), [])
  results.push({ scenario: 'Offline app reload works while unlocked; logout purges private data and retains only quarantined owner-bound work; B cannot review A files', passed: true })

  await login(page, 'A'); await warm(page); await share(page)
  const second = await harness(context)
  await second.waitForFunction(() => gc011.auth.isAuthenticated)
  await page.evaluate(() => { window.late = fetch('/api/vehicles?gc011=late').then(async r => ({ status: r.status, text: await r.text() })) })
  await until(() => lateSeen, 'old response ready')
  await page.evaluate(() => gc011.auth.logout()); await login(page, 'B')
  lateResponse()
  assert.equal((await page.evaluate(() => window.late)).status, 409)
  await second.waitForFunction(() => !gc011.auth.isAuthenticated)
  assert.equal(await second.evaluate(async () => (await fetch('/api/vehicles')).status), 409)
  assert.equal(await page.evaluate(async () => (await gc011.workerMessage('TAKE_SHARED_RECEIPT')).receipt), null)
  data = await inventory(page)
  const current = data.state.find(row => row.key === 'active')
  assert(data.caches.filter(name => name.startsWith('gearcargo-private-')).every(name => name.includes(current.identity.owner_key)))
  await second.close()
  results.push({ scenario: 'A→B clears shared receipts and other tabs; late A response cannot repopulate caches or reach B', passed: true })

  await warm(page)
  await page.evaluate(async () => { history.replaceState(null, '', '/login'); try { await gc011.api.get('/vehicles?gc011=expire') } catch { /* Expected expiry. */ } })
  await page.waitForFunction(() => !gc011.auth.isAuthenticated)
  assertPurged(await inventory(page))
  results.push({ scenario: 'Definitive session expiry purges cache/profile and clears the UI even on the login page', passed: true })

  await login(page, 'A'); await warm(page)
  await page.evaluate(async () => { const state = await gc011.getQueueState(); await gc011.mutationDb.state.put({ ...state, privateUntil: Date.now() - 1 }) })
  await context.setOffline(true)
  const expired = await context.newPage(); await expired.goto(`${origin}/vehicles`)
  await expired.waitForURL('**/login', { timeout: 15000 })
  await until(async () => !(await inventory(page)).caches.some(name => name.startsWith('gearcargo-private-')), 'offline expiry cleanup')
  assertPurged(await inventory(page))
  await expired.close(); await context.setOffline(false)
  results.push({ scenario: 'Expired offline profile cannot unlock on reload; private data is purged and the offline login shell remains', passed: true })
  await login(page, 'A'); await warm(page)
  const failedCleanup = await page.evaluate(async () => {
    const prototype = Object.getPrototypeOf(caches), remove = prototype.delete
    prototype.delete = async function (name) { if (name.startsWith('gearcargo-private-')) throw new Error('Injected cleanup failure'); return remove.call(this, name) }
    try { await gc011.auth.login('queue-b@example.invalid', 'BrowserFixture123!'); return false } catch { return true } finally { prototype.delete = remove }
  })
  assert(failedCleanup)
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/auth/me')).json()).username), 'queue_A')
  await login(page, 'B')
  results.push({ scenario: 'Cleanup failure blocks account switching before cookie changes; retry completes cleanup', passed: true })
  await context.close()
  console.log(JSON.stringify(results, null, 2))
} finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
