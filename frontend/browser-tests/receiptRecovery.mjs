/* eslint-disable no-undef */
// Real Chromium + built service worker + Flask cookie-authentication acceptance.
// See docs/RECEIPT_DRAFTS.md and docs/OFFLINE_RECOVERY.md for the isolated fixture.
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
  await build({ entryPoints: [join(source, 'browser-tests/receiptHarness.jsx')], bundle: true,
    outfile: join(output, `${label}-harness.js`), format: 'esm', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
}

let served = mode === 'before' ? before : root
let servedLabel = mode === 'before' ? 'before' : 'fixed'
let blockWrites = false, uploadStatus = null, linkConflict = false, loseUpload = false
let uploadRequests = 0, uploadedResponses = 0
const ordinaryWrite = req => req.method !== 'GET' && /^\/api\/(fuel|attachments)(\/|$)/.test(req.url)
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
      if (req.method === 'POST' && req.url === '/api/attachments') {
        uploadRequests++
        if (uploadStatus) { res.writeHead(uploadStatus, { 'Content-Type': 'application/json' }); res.end('{}'); return }
      }
      if (linkConflict && req.method === 'PUT' && /^\/api\/attachments\/\d+$/.test(req.url)) {
        res.writeHead(409, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ code: 'REVISION_CONFLICT', current: { revision: 1, vehicle_id: 1, entry_id: null } })); return
      }
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: { ...req.headers, 'x-gc007-fixture': 'disposable-browser-only' } }, response => {
        if (req.method === 'POST' && req.url === '/api/attachments' && response.statusCode === 201) {
          uploadedResponses++
          if (loseUpload) {
            loseUpload = false
            uploadStatus = 500
            response.resume()
            response.on('end', () => req.socket.destroy())
            return
          }
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
    res.end(path === '/sw.js' ? Buffer.concat([Buffer.from('delete Object.getPrototypeOf(self.registration).sync;\n'), content]) : content)
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
async function pageIn(context, register = true, fuel = null) {
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => results.push({ browserError: error.message }))
  await page.goto(`${origin}/api/auth/queue-test${fuel ? '?fuel=' + fuel : ''}`)
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
const PDF = '%PDF-1.4\n% original offline receipt\n%%EOF\n'
async function localRows(page) {
  return page.evaluate(async () => {
    const db = await new Promise(resolve => { const r = indexedDB.open('GearCargoMutationIdentity'); r.onsuccess = () => resolve(r.result) })
    try { return await new Promise(resolve => { const r = db.transaction('receipts').objectStore('receipts').getAll(); r.onsuccess = () => resolve(r.result.map(({ blob, ...row }) => ({ ...row, bytes: blob?.size }))) }) }
    finally { db.close() }
  })
}
async function force(page) { return message(page, { type: 'FORCE_SYNC', identity: await identity(page) }) }
async function review(page, type, row) { return message(page, { type: 'REVIEW_RECEIPTS', identity: await identity(page), action: { type, id: row?.id, version: row?.version } }) }
async function save(page, vehicle, name, extra = {}) {
  return page.evaluate(async ({ vehicle, name, text, extra }) => window.gc010.save({ resource: 'fuel', payload: { vehicle_id: vehicle, liters: 10, total_price: 20, notes: name },
    config: window.gc007.mutationOptions(), file: new File([text], 'original.pdf', { type: 'application/pdf' }), ...extra }), { vehicle, name, text: PDF, extra })
}
async function counts(page, note) {
  return page.evaluate(async note => {
    const entries = (await window.gc007.api.get('/fuel')).data.entries.filter(row => row.notes === note)
    const attachments = (await window.gc007.api.get('/attachments')).data.attachments
    return { entries, attachments }
  }, note)
}
async function finish(page) { await until(async () => { await force(page); return (await localRows(page)).length === 0 }, 'receipt linked') }
let context
async function reopenBrowser() {
  const next = await chromium.launchPersistentContext(join(output, 'profile'), { headless: true,
    executablePath: process.env.GC_CHROMIUM || undefined, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
  await next.addInitScript(() => { if (globalThis.ServiceWorkerRegistration) delete ServiceWorkerRegistration.prototype.sync })
  return next
}
try {
  context = await reopenBrowser()
  let page = await pageIn(context)
  await login(page, 'A')
  const vehicle = await page.evaluate(async () => (await window.gc007.api.post('/vehicles', { name: 'Receipt car', make: 'Test', model: 'Fixture', fuel_type: 'petrol' })).data.vehicle)
  assert.equal(await context.serviceWorkers()[0].evaluate(() => 'sync' in self.registration), false)

  // Exercise the actual form and File handoff, then close the application tab.
  const form = await pageIn(context, true, vehicle.id)
  await form.locator('input[name="mileage"]').fill('123')
  await form.locator('input[name="liters"]').fill('10')
  await form.locator('input[name="price_per_liter"]').fill('2')
  await form.locator('textarea[name="notes"]').fill('GC010 offline form')
  blockWrites = true
  await context.setOffline(true)
  await form.locator('input[type="file"]').first().setInputFiles({ name: 'original.pdf', mimeType: 'application/pdf', buffer: Buffer.from(PDF) })
  await form.locator('button.btn-primary').first().click()
  await until(async () => (await localRows(form)).length === 1, 'atomic parent and Blob save')
  assert.equal((await rows(form)).length, 1)
  const saved = (await localRows(form))[0]
  assert.equal(saved.bytes, Buffer.byteLength(PDF))
  await form.close(); await page.close(); await context.close()
  console.log('Application and browser closed after durable save')
  blockWrites = false
  context = await reopenBrowser()
  page = await pageIn(context)
  await finish(page)
  const offline = await counts(page, 'GC010 offline form')
  assert.equal(offline.entries.length, 1)
  assert.equal(offline.attachments.length, 1)
  assert.equal(offline.attachments[0].entry_id, offline.entries[0].id)
  assert.equal(await page.evaluate(async id => (await fetch(`/api/attachments/${id}/download`)).text(), offline.attachments[0].id), PDF)
  results.push({ scenario: 'Real expense form: offline File, tab close, worker restart, reconnect, original bytes linked exactly once', passed: true })

  for (const status of [413, 500]) {
    uploadStatus = status
    assert.equal((await save(page, vehicle.id, `GC010 upload ${status}`)).receiptPending, true)
    let draft = (await localRows(page))[0]
    assert(draft.parentId && draft.bytes === Buffer.byteLength(PDF))
    await page.getByText('Expense saved; receipt not attached yet', { exact: false }).first().waitFor()
    const originalKey = draft.uploadKey
    await page.goto(`${origin}/api/auth/queue-test`)
    await page.waitForFunction(() => window.gc010 && window.gc007.auth.user)
    draft = (await localRows(page))[0]
    assert.equal(draft.uploadKey, originalKey)
    await page.getByText('Receipts waiting to attach', { exact: false }).first().waitFor()
    const downloaded = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download original' }).click()
    const file = await downloaded
    assert.equal((await readFile(await file.path())).toString(), PDF)
    await page.screenshot({ path: join(output, `receipt-${status}.png`), fullPage: true })
    uploadStatus = null
    assert.equal((await review(page, 'retry', draft)).success, true)
    await finish(page)
    const after = await counts(page, `GC010 upload ${status}`)
    assert.equal(after.entries.length, 1)
    assert.equal(after.attachments.filter(row => row.entry_id === after.entries[0].id).length, 1)
    results.push({ scenario: `Upload ${status}: visible pending status, reload, original download and same-key retry`, passed: true })
  }

  const beforeScan = (await counts(page, '')).attachments.length
  await page.evaluate(async ({ vehicle, text }) => {
    const file = new File([text], 'scanned.pdf', { type: 'application/pdf' })
    await window.gc010.attachmentApi.upload(file, { vehicleId: vehicle,
      operationKey: window.gc010.receiptUploadKey(file), identity: window.gc010.getBoundIdentity() })
    // Simulate the OCR response having committed before its callback hands off
    // an ID: save must reuse the upload identity instead of creating an orphan.
    await window.gc010.save({ resource: 'fuel', payload: { vehicle_id: vehicle, liters: 10, total_price: 20, notes: 'GC010 OCR handoff' },
      config: window.gc007.mutationOptions(), file })
  }, { vehicle: vehicle.id, text: PDF })
  await finish(page)
  const scanned = await counts(page, 'GC010 OCR handoff')
  assert.equal(scanned.attachments.length, beforeScan + 1)
  assert.equal(scanned.attachments.filter(row => row.entry_id === scanned.entries[0].id).length, 1)
  results.push({ scenario: 'OCR upload/expense-save race shares the original upload key and leaves no duplicate file', passed: true })

  linkConflict = true
  assert.equal((await save(page, vehicle.id, 'GC010 link conflict')).receiptPending, true)
  let draft = (await localRows(page))[0]
  assert.equal(draft.status, 'mutation_conflict')
  assert(draft.attachmentId && draft.bytes)
  const beforeRetry = uploadRequests
  linkConflict = false
  // The fixture supplies the real initial upload revision (1); PDFs may finish
  // extraction meanwhile, so refresh the conflict through the real endpoint.
  await review(page, 'retry', draft)
  await force(page)
  draft = (await localRows(page))[0]
  if (draft) { assert.equal(draft.status, 'mutation_conflict'); await review(page, 'retry', draft) }
  await finish(page)
  assert.equal(uploadRequests, beforeRetry)
  results.push({ scenario: 'Link 409 retains Blob and uploaded ID; explicit retry links without another upload', passed: true })

  const attachmentsBeforeLoss = (await counts(page, '')).attachments.length
  loseUpload = true
  await save(page, vehicle.id, 'GC010 lost upload response')
  draft = (await localRows(page))[0]
  assert(draft && draft.bytes)
  uploadStatus = null
  await review(page, 'retry', draft)
  await finish(page)
  const lost = await counts(page, 'GC010 lost upload response')
  assert.equal(lost.entries.length, 1)
  assert.equal(lost.attachments.length, attachmentsBeforeLoss + 1)
  assert.equal(lost.attachments.filter(row => row.entry_id === lost.entries[0].id).length, 1)
  assert(uploadedResponses >= 2)
  results.push({ scenario: 'Upload commits then response is lost: persistent key prevents duplicate files', passed: true })

  blockWrites = true; await context.setOffline(true)
  await save(page, vehicle.id, 'GC010 A private receipt')
  const aDraft = (await localRows(page))[0]
  const requestsBeforeSwitch = uploadRequests
  await page.evaluate(() => window.gc007.auth.logout())
  await context.setOffline(false); await login(page, 'B'); blockWrites = false
  await force(page)
  assert.equal(uploadRequests, requestsBeforeSwitch)
  assert.deepEqual((await review(page, 'list')).entries, [])
  await login(page, 'A')
  const owned = (await review(page, 'list')).entries
  assert(owned.some(row => row.id === aDraft.id && row.hasFile))
  assert.equal((await review(page, 'remove', owned[0])).success, true)
  results.push({ scenario: 'Account switch neither uploads nor discloses the prior account file; original owner can remove it', passed: true })

  // An IDB quota failure must abort BOTH writes and leave the form's File usable.
  const worker = context.serviceWorkers()[0]
  await worker.evaluate(() => {
    self.gc010Put = IDBObjectStore.prototype.add
    IDBObjectStore.prototype.add = function (...args) { if (this.name === 'receipts') throw new DOMException('test quota', 'QuotaExceededError'); return self.gc010Put.apply(this, args) }
  })
  const beforePending = (await rows(page)).length
  let quotaFailed = false
  try { await save(page, vehicle.id, 'GC010 quota failure') } catch { quotaFailed = true }
  assert(quotaFailed)
  assert.equal((await rows(page)).length, beforePending)
  assert.equal((await localRows(page)).length, 0)
  await worker.evaluate(() => { IDBObjectStore.prototype.add = self.gc010Put })
  results.push({ scenario: 'Quota failure atomically aborts parent and receipt; no false saved result', passed: true })
  await context.close()
  console.log(JSON.stringify(results, null, 2))
} catch (error) { console.log(JSON.stringify(results, null, 2)); throw error } finally {
  await context?.close().catch(() => {}); await browser.close(); await new Promise(resolve => server.close(resolve))
}
