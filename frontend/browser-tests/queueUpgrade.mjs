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

let served = before
let servedLabel = 'before'
let blockWrites = false
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
assert(before, 'Set GC_BEFORE_FRONTEND to the built pre-GC009 frontend')
try {
  const context = await browser.newContext()
  let page = await pageIn(context)
  await login(page, 'A')
  const scope = await identity(page)
  blockWrites = true
  await page.evaluate(async () => { try { await window.gc007.api.post('/vehicles', { name: 'GC009 version-two upgrade', make: 'Test', model: 'Fixture', fuel_type: 'petrol' }) } catch { /* legacy network failure */ } })
  await until(async () => (await rows(page)).length === 1, 'old queue')
  const old = (await rows(page))[0]
  assert.equal(old.metadata.version, 2)
  served = root; servedLabel = 'fixed'
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
  await message(page, { type: 'GET_PENDING_SYNC_COUNT', identity: scope })
  const upgraded = (await rows(page))[0]
  assert.equal(upgraded.metadata.version, 3)
  assert.equal(upgraded.metadata.operationId, old.metadata.operationId)
  assert.equal(upgraded.body, old.body)
  assert.deepEqual(upgraded.metadata.identity, old.metadata.identity)
  // Repeat migration/startup: no duplicate and no new key after interruption.
  const cdp = await context.newCDPSession(page)
  await cdp.send('ServiceWorker.enable'); await cdp.send('ServiceWorker.stopAllWorkers'); await cdp.detach()
  await message(page, { type: 'GET_PENDING_SYNC_COUNT', identity: scope })
  assert.equal((await rows(page)).length, 1)
  blockWrites = false
  const result = await message(page, { type: 'FORCE_SYNC', identity: scope })
  assert.equal(result.success, true)
  assert.equal(result.committedCount, 1)
  await sync(page)
  const list = await page.evaluate(async () => (await window.gc007.api.get('/vehicles')).data.vehicles)
  assert.equal(list.filter(row => row.name === 'GC009 version-two upgrade').length, 1)
  assert.equal((await rows(page)).length, 0)
  results.push({ scenario: 'Real GC008 worker upgrade: pending body/key/owner preserved; restart and repeated replay create one record', passed: true })
  console.log(JSON.stringify(results, null, 2))
  await context.close()
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
