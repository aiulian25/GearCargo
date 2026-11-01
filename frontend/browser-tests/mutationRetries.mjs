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
  await build({ entryPoints: [join(source, 'browser-tests/mutationHarness.jsx')], bundle: true,
    outfile: join(output, `${label}-harness.js`), format: 'esm', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
}

let served = mode === 'before' ? before : root
let servedLabel = mode === 'before' ? 'before' : 'fixed'
let blockWrites = false
let loseFuelResponse = false
let committedFuelResponse
let committedFuelKey
const ordinaryWrite = req => req.method !== 'GET' && /^\/api\/(vehicles|fuel|todos)(\/|$)/.test(req.url)
const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/auth/queue-test')) {
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
        if (loseFuelResponse && req.url === '/api/fuel' && req.method === 'POST') {
          loseFuelResponse = false
          blockWrites = true
          committedFuelKey = req.headers['idempotency-key']
          const chunks = []
          response.on('data', chunk => chunks.push(chunk))
          response.on('end', () => { committedFuelResponse = Buffer.concat(chunks).toString(); req.socket.destroy() })
          return
        }
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
async function pageIn(context, register = true, edit = null) {
  const page = await context.newPage()
  page.on('pageerror', error => results.push({ browserError: error.message }))
  await page.goto(`${origin}/api/auth/queue-test${edit ? '?edit=' + edit : ''}`)
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
try {
  const context = await browser.newContext()
  const page = await pageIn(context)
  await login(page, 'A')
  const vehicle = await page.evaluate(async () => (await window.gc007.api.post('/vehicles', { name: 'Two editors', make: 'Test', model: 'Fixture', fuel_type: 'petrol' })).data.vehicle)
  loseFuelResponse = true
  const lost = await page.evaluate(async vehicleId => {
    const payload = { vehicle_id: vehicleId, liters: 10, total_price: 20 }
    const config = window.gc007.mutationOptions()
    window.retryFuel = { payload, config }
    try { await window.gc007.api.post('/fuel', payload, config); return false } catch { return true }
  }, vehicle.id)
  assert(lost && committedFuelResponse, 'The fixture must lose a response after the server commits')
  await until(async () => (await rows(page)).length === 1, 'durable queued expense')
  const queued = (await rows(page))[0]
  assert.equal(queued.metadata.version, 3)
  assert.equal(queued.metadata.operationId, committedFuelKey)
  blockWrites = false
  await sync(page)
  await until(async () => (await rows(page)).length === 0, 'retry drains the queue')
  const replay = await page.evaluate(async () => {
    const { payload, config } = window.retryFuel
    const response = await window.gc007.api.post('/fuel', payload, config)
    const list = await window.gc007.api.get('/fuel')
    return { body: response.data, status: response.status, replayed: response.headers['idempotent-replay'], entries: list.data.entries }
  })
  assert.equal(replay.status, 201)
  assert.equal(replay.replayed, 'true')
  assert.deepEqual(replay.body, JSON.parse(committedFuelResponse))
  assert.equal(replay.entries.length, 1)
  results.push({ scenario: 'Commit then lost response, worker replay and manual retry', expenses: replay.entries.length, exactResponse: true })

  const editorA = await pageIn(context, true, vehicle.id)
  const editorB = await pageIn(context, true, vehicle.id)
  const inputA = editorA.locator('input[name="name"]')
  const inputB = editorB.locator('input[name="name"]')
  await inputA.waitFor(); await inputB.waitFor()
  await inputA.fill('Saved by first editor')
  await inputB.fill('Unsaved second editor')
  const saved = editorA.waitForResponse(r => r.url().endsWith(`/api/vehicles/${vehicle.id}`) && r.request().method() === 'PUT')
  await editorA.locator('button.btn-primary').first().click()
  assert.equal((await saved).status(), 200)
  const rejected = editorB.waitForResponse(r => r.url().endsWith(`/api/vehicles/${vehicle.id}`) && r.request().method() === 'PUT')
  await editorB.locator('button.btn-primary').first().click()
  const conflict = await rejected
  assert.equal(conflict.status(), 409)
  assert.equal((await conflict.json()).current.name, 'Saved by first editor')
  await editorB.getByText('This record changed after you opened it. Reload and review before saving.').first().waitFor()
  assert.equal(await inputB.inputValue(), 'Unsaved second editor')
  await editorB.screenshot({ path: join(output, 'stale-editor.png'), fullPage: true })
  results.push({ scenario: 'Two real edit forms in separate tabs', first: 200, stale: 409, draftRetained: true, conflictVisible: true })

  // A stale offline update must remain reviewable instead of claiming success.
  blockWrites = true
  const scope = await identity(page)
  const originalRevision = vehicle.revision
  await page.evaluate(async ({ id, revision }) => {
    try { await window.gc007.api.put(`/vehicles/${id}`, { name: 'Queued stale draft' }, window.gc007.mutationOptions(revision)) } catch { /* transport failure */ }
  }, { id: vehicle.id, revision: originalRevision })
  await until(async () => (await rows(page)).length === 1, 'queued stale edit')
  blockWrites = false
  await sync(page)
  await until(async () => (await rows(page)).length === 0, 'conflict moved to review')
  const held = await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action: 'export', identity: scope })
  assert(held.entries.some(entry => entry.reason === 'mutation_conflict' && entry.body.includes('Queued stale draft')))
  results.push({ scenario: 'Offline revision conflict', retainedForReview: true })
  console.log(JSON.stringify(results, null, 2))
  await context.close()
} finally {
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
