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
  await build({ entryPoints: [join(source, 'browser-tests/recoveryHarness.jsx')], bundle: true,
    outfile: join(output, `${label}-harness.js`), format: 'esm', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
}

let served = mode === 'before' ? before : root
let servedLabel = mode === 'before' ? 'before' : 'fixed'
let blockWrites = false
let responseStatus = null
let noSync = true
let workerRevision = 0
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
      if (responseStatus && ordinaryWrite(req)) { res.writeHead(responseStatus, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: '<script>private diagnostic</script>' })); return }
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
    const content = await readFile(file)
    res.end(path === '/sw.js' ? Buffer.concat([Buffer.from(`${noSync ? 'delete Object.getPrototypeOf(self.registration).sync;' : ''}\n// fixture worker ${workerRevision}\n`), content]) : content)
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
async function held(page) { return (await message(page, { type: 'REVIEW_OFFLINE_QUEUE', identity: await identity(page), action: 'list' })).entries }
async function force(page) { return page.evaluate(() => window.gc009.sync.triggerSync()) }
async function queueDraft(page, name) {
  blockWrites = true
  assert.equal(await page.evaluate(async name => {
    try { await window.gc007.api.post('/vehicles', { name, make: 'Test', model: 'Fixture', fuel_type: 'petrol' }, window.gc007.mutationOptions()); return 'saved' }
    catch (error) { return error.code }
  }, name), 'OFFLINE_QUEUED')
  assert((await rows(page)).some(row => row.body.includes(name)))
}
async function updateWorker(page) {
  workerRevision++
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration()
    await registration.update()
    if (!registration.waiting) await new Promise(resolve => {
      const installing = registration.installing
      if (installing.state === 'installed') resolve()
      else installing.addEventListener('statechange', () => { if (installing.state === 'installed') resolve() })
    })
    const changed = new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }))
    registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    await changed
  })
}
const names = async page => (await page.evaluate(async () => (await window.gc007.api.get('/vehicles')).data.vehicles)).map(row => row.name)
async function reload(page) { await page.goto(`${origin}/api/auth/queue-test`); await page.waitForFunction(() => window.gc009 && window.gc007.auth.user) }
async function editDraft(page, name) {
  await page.getByRole('button', { name: 'Review drafts', exact: true }).click()
  await page.getByRole('button', { name: 'Review this draft', exact: true }).click()
  await page.getByLabel('Name', { exact: true }).fill(name)
  await page.screenshot({ path: join(output, name.includes('conflict') ? 'recovery-conflict.png' : 'recovery-validation.png'), fullPage: true })
  await page.getByRole('button', { name: 'Queue reviewed change' }).click()
  await until(async () => (await held(page)).length === 0, 'edited draft queued')
}
try {
  let page
  if (process.env.GC_RECOVERY_SCENARIO !== 'tabless') {
  const context = await browser.newContext()
  await context.addInitScript(() => { if (globalThis.ServiceWorkerRegistration) delete ServiceWorkerRegistration.prototype.sync })
  page = await pageIn(context)
  await login(page, 'A')
  assert.equal(await page.evaluate(async () => 'sync' in await navigator.serviceWorker.ready), false)
  assert.equal(await context.serviceWorkers()[0].evaluate(() => 'sync' in self.registration), false)
  await queueDraft(page, 'GC009 validation draft')
  responseStatus = 422; blockWrites = false
  assert.equal(await force(page), false)
  assert.equal((await held(page))[0].reason, 'validation_failed')
  assert.equal(await page.evaluate(() => window.gc009.sync.lastSyncTime?.getTime() ?? null), null)
  assert(!JSON.stringify(await held(page)).includes('private diagnostic'))
  await reload(page)
  responseStatus = null
  await editDraft(page, 'GC009 repaired validation')
  assert.equal(await force(page), true)
  assert.equal((await names(page)).filter(name => name === 'GC009 repaired validation').length, 1)
  const firstCommit = await page.evaluate(() => window.gc009.sync.lastSyncTime?.getTime() ?? null)
  assert(firstCommit)
  await reload(page)
  await page.waitForFunction(() => window.gc009?.sync.lastSyncTime)
  assert.equal(await page.evaluate(() => window.gc009.sync.lastSyncTime?.getTime() ?? null), firstCommit)
  results.push({ scenario: 'No SyncManager: acknowledged storage, 422, reload, visible repair, committed timestamp', passed: true })

  const vehicle = await page.evaluate(async () => (await window.gc007.api.post('/vehicles', { name: 'GC009 before conflict', make: 'Test', model: 'Fixture', fuel_type: 'petrol' })).data.vehicle)
  await page.evaluate(async vehicle => window.gc007.api.put(`/vehicles/${vehicle.id}`, { name: 'GC009 concurrent edit' }, window.gc007.mutationOptions(vehicle)), vehicle)
  blockWrites = true
  await page.evaluate(async vehicle => { try { await window.gc007.api.put(`/vehicles/${vehicle.id}`, { name: 'GC009 conflict draft' }, window.gc007.mutationOptions(vehicle)) } catch { /* queued */ } }, vehicle)
  blockWrites = false
  assert.equal(await force(page), false)
  const conflict = (await held(page))[0]
  assert.equal(conflict.error.code, 'REVISION_CONFLICT')
  assert.equal(conflict.current.name, 'GC009 concurrent edit')
  await updateWorker(page)
  assert.equal((await held(page))[0].body, conflict.body)
  await reload(page)
  await editDraft(page, 'GC009 conflict resolved')
  assert.equal(await force(page), true)
  assert((await names(page)).includes('GC009 conflict resolved'))
  results.push({ scenario: 'Actual 409 conflict, worker update, visible comparison and repair', passed: true })

  await queueDraft(page, 'GC009 needs reauthentication')
  responseStatus = 401; blockWrites = false
  assert.equal(await force(page), false)
  const paused = (await held(page))[0]
  assert.equal(paused.reason, 'sign_in_required')
  responseStatus = null
  const action = { type: 'resume', id: paused.id, version: paused.version }
  assert((await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action, identity: await identity(page) })).error.includes('Sign in again'))
  await login(page, 'B')
  assert.deepEqual(await held(page), [])
  assert.equal((await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action, identity: await identity(page) })).success, false)
  await login(page, 'A')
  assert.equal((await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action, identity: await identity(page) })).success, true)
  assert.equal(await force(page), true)
  assert.equal((await names(page)).filter(name => name === 'GC009 needs reauthentication').length, 1)
  results.push({ scenario: '401 requires same-owner reauthentication; another account cannot inspect or resume', passed: true })

  for (const status of [429, 500, 'network']) {
    await queueDraft(page, `GC009 retry ${status}`)
    if (status !== 'network') { responseStatus = status; blockWrites = false }
    const commitBefore = await page.evaluate(() => window.gc009.sync.lastSyncTime?.getTime() ?? null)
    assert.equal(await force(page), false)
    assert.equal((await rows(page)).length, 1)
    const pending = (await rows(page))[0]
    assert(pending.metadata.retryAt > Date.now())
    assert.equal(await page.evaluate(() => window.gc009.sync.lastSyncTime?.getTime() ?? null), commitBefore)
    await reload(page)
    assert.equal((await rows(page))[0].metadata.operationId, pending.metadata.operationId)
    responseStatus = null; blockWrites = false
    await until(async () => { await force(page); return !(await rows(page)).length }, `retry ${status}`)
    assert.equal((await names(page)).filter(name => name === `GC009 retry ${status}`).length, 1)
    results.push({ scenario: `${status}: reload preserves draft and key; retry creates one record`, passed: true })
  }

  await queueDraft(page, 'GC009 old draft')
  await page.evaluate(async () => {
    const db = await new Promise(resolve => { const r = indexedDB.open('GearCargoMutationIdentity'); r.onsuccess = () => resolve(r.result) })
    await new Promise(resolve => { const tx = db.transaction('pending', 'readwrite'), store = tx.objectStore('pending'); const r = store.getAll(); r.onsuccess = () => { for (const row of r.result) store.put({ ...row, timestamp: Date.now() - 86400001 }) }; tx.oncomplete = resolve })
    db.close()
  })
  await message(page, { type: 'GET_PENDING_SYNC_COUNT', identity: await identity(page) })
  const expired = (await held(page))[0]
  assert.equal(expired.reason, 'retention_expired')
  assert(expired.body.includes('GC009 old draft'))
  blockWrites = false
  await message(page, { type: 'REVIEW_OFFLINE_QUEUE', action: { type: 'resume', id: expired.id, version: expired.version }, identity: await identity(page) })
  assert.equal(await force(page), true)
  results.push({ scenario: '24-hour deadline retains draft for explicit resume/export', passed: true })

  const fuelVehicle = await page.evaluate(async () => (await window.gc007.api.get('/vehicles')).data.vehicles[0])
  loseFuelResponse = true
  await page.evaluate(async id => { try { await window.gc007.api.post('/fuel', { vehicle_id: id, liters: 7, total_price: 14 }, window.gc007.mutationOptions()) } catch { /* queued */ } }, fuelVehicle.id)
  assert(committedFuelResponse && committedFuelKey)
  assert.equal((await rows(page))[0].metadata.operationId, committedFuelKey)
  const cdp = await context.newCDPSession(page)
  await cdp.send('ServiceWorker.enable'); await cdp.send('ServiceWorker.stopAllWorkers'); await cdp.detach()
  blockWrites = false
  await until(() => force(page), 'replay after the terminated worker lease expires')
  assert.equal(await page.evaluate(async () => (await window.gc007.api.get('/fuel')).data.entries.filter(row => row.liters === 7).length), 1)
  results.push({ scenario: 'Committed response lost; worker restart and same-key retry create no duplicate', passed: true })
  await context.close()
  }

  noSync = false
  const background = await browser.newContext()
  page = await pageIn(background)
  await login(page, 'A')
  await background.setOffline(true)
  await queueDraft(page, 'GC009 no open app tab')
  const driver = await background.newPage(), session = await background.newCDPSession(driver)
  let registrationId
  session.on('ServiceWorker.workerRegistrationUpdated', ({ registrations }) => { registrationId = registrations.find(reg => reg.scopeURL === origin + '/')?.registrationId || registrationId })
  await session.send('ServiceWorker.enable')
  await until(() => registrationId, 'background registration')
  await page.close()
  assert.equal(await background.serviceWorkers()[0].evaluate(async () => (await self.clients.matchAll()).length), 0)
  blockWrites = false
  await background.setOffline(false)
  await session.send('ServiceWorker.dispatchSyncEvent', { origin, registrationId, tag: 'workbox-background-sync:gearcargo-account-queue-v1', lastChance: true })
  await until(async () => (await (await fetch(`${origin}/__gc007/records`)).json()).A.includes('GC009 no open app tab'), 'tabless sync')
  await Promise.all([1, 2, 3].map(() => session.send('ServiceWorker.dispatchSyncEvent', { origin, registrationId, tag: 'workbox-background-sync:gearcargo-account-queue-v1', lastChance: true })))
  assert.equal((await (await fetch(`${origin}/__gc007/records`)).json()).A.filter(name => name === 'GC009 no open app tab').length, 1)
  await session.detach(); await background.close()
  results.push({ scenario: 'No open app tab and repeated native sync events', passed: true })
  console.log(JSON.stringify(results, null, 2))
} catch (error) { console.log(JSON.stringify(results, null, 2)); throw error } finally {
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
