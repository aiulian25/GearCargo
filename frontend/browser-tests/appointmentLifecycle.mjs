/* eslint-disable no-undef */
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-workshop-proposal4/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/appointmentHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
let blockCreates = false
const errors = []
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/api/auth/appointment-test') {
      res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><div id="root"></div><script type="module" src="/__appointment-harness.js"></script>'); return
    }
    if (req.url === '/__appointment-harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    if (req.url.startsWith('/api/')) {
      if (blockCreates && req.method === 'POST' && req.url === '/api/appointments') { req.socket.destroy(); return }
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method, path: req.url, headers: req.headers }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
      proxy.on('error', () => { res.statusCode = 502; res.end() }); req.pipe(proxy); return
    }
    const file = join(root, 'dist', req.url.split('?')[0])
    res.setHeader('Content-Type', ({ '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.webmanifest': 'application/manifest+json' })[extname(file)] || 'application/octet-stream')
    res.end(await readFile(file))
  } catch { res.statusCode = 404; res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
try {
  const context = await browser.newContext({ viewport: { width: 1100, height: 1000 } })
  let page = await context.newPage()
  const open = async () => {
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(origin + '/api/auth/appointment-test')
    await page.waitForFunction(() => window.appointmentFixture && !window.appointmentFixture.auth.isLoading)
    await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
    await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  }
  const until = async check => {
    const deadline = Date.now() + 45000
    while (!(await check())) {
      if (Date.now() > deadline) throw new Error('Timed out waiting for committed offline request')
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }
  const go = async path => page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
  const save = async endpoint => {
    const [response] = await Promise.all([page.waitForResponse(r => r.url().endsWith(endpoint) && ['POST','PUT'].includes(r.request().method())), page.getByRole('button', { name: 'Save', exact: true }).click()])
    assert.ok([200,201].includes(response.status()), await response.text())
    await page.getByRole('form').waitFor({ state: 'detached' })
  }
  await open()
  await page.evaluate(() => window.appointmentFixture.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.appointmentFixture.auth.isAuthenticated)
  await go('/vehicles/1/appointments')
  const fill = async title => {
    await page.getByRole('button', { name: 'Plan workshop visit' }).click()
    await page.getByLabel('Visit title').fill(title)
    await page.getByLabel('Workshop name').fill('Local garage')
    await page.getByLabel('Time zone', { exact: true }).fill('Europe/London')
    await page.getByLabel('Proposed drop-off').fill('2027-06-15T09:30')
    await page.getByLabel('Proposed pick-up').fill('2027-06-15T17:00')
  }
  await fill('Annual workshop visit')
  await page.getByRole('button', { name: 'Inspect brakes', exact: true }).click()
  await save('/api/appointments')
  await page.getByText('Requested · not confirmed', { exact: true }).waitFor()
  const act = async (label, endpoint) => {
    await page.getByRole('button', { name: label, exact: true }).click()
    const [response] = await Promise.all([page.waitForResponse(r => r.url().endsWith(endpoint) && r.request().method() === 'POST'), page.getByRole('button', { name: 'Confirm', exact: true }).click()])
    assert.equal(response.status(), 200, await response.text())
    await page.getByRole('dialog').waitFor({ state: 'detached' })
  }
  await act('Mark confirmed', '/api/appointments/1/confirm')
  await act('Record drop-off', '/api/appointments/1/dropoff')
  await page.getByRole('button', { name: 'Complete visit', exact: true }).click()
  await page.getByLabel('Workshop invoice · 2026-11-01 · 230 GBP').check()
  await page.getByLabel('Inspect brakes', { exact: true }).check()
  const [completed] = await Promise.all([page.waitForResponse(r => r.url().endsWith('/api/appointments/1/complete')), page.getByRole('button', { name: 'Complete visit', exact: true }).click()])
  assert.equal(completed.status(), 200, await completed.text())
  await page.getByRole('form').waitFor({ state: 'detached' })
  const visit = await page.evaluate(async () => (await window.appointmentFixture.api.get('/appointments/1')).data)
  assert.equal(visit.status, 'completed'); assert.equal(visit.expenses.length, 1); assert.equal(visit.expenses[0].entry_id, 1)
  assert.equal(visit.start_at, '2027-06-15T08:30:00Z'); assert.ok(visit.dropoff_at && visit.pickup_at)
  assert.equal(await page.evaluate(async () => (await window.appointmentFixture.api.get('/todos/1')).data.completed), true)
  await fill('Offline workshop request')
  blockCreates = true
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('form').waitFor({ state: 'detached' })
  await until(() => page.evaluate(async () => (await window.appointmentFixture.mutationDb.pending.count()) === 1))
  await page.close(); page = await context.newPage(); await open()
  assert.equal(await page.evaluate(() => window.appointmentFixture.mutationDb.pending.count()), 1)
  blockCreates = false
  await until(() => page.evaluate(async () => {
    const channel = new MessageChannel()
    await new Promise((resolve, reject) => { channel.port1.onmessage = e => e.data?.error ? reject(new Error(e.data.error)) : resolve(e.data); navigator.serviceWorker.controller.postMessage({ type: 'FORCE_SYNC' }, [channel.port2]) })
    return (await window.appointmentFixture.api.get('/appointments?vehicle_id=1')).data.appointments.length === 2
  }))
  assert.equal(await page.evaluate(() => window.appointmentFixture.mutationDb.pending.count()), 0)
  await go('/vehicles/1/appointments')
  await page.getByRole('heading', { name: 'Offline workshop request' }).waitFor()
  await page.getByText('Requested · not confirmed', { exact: true }).waitFor()
  await act('Cancel visit', '/api/appointments/2/cancel')
  await page.getByText('Cancelled', { exact: true }).waitFor()
  await page.screenshot({ path: join(output, 'desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false)
  await page.screenshot({ path: join(output, 'mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ passed: ['manual request and owner confirmation', 'drop-off and completion through real forms', 'selected task resolution and single expense link', 'correct named-zone UTC instant', 'offline request persists across restart and replays once', 'cancellation and responsive layouts'], browserErrors: errors }, null, 2))
  console.log('6 browser acceptance checks passed')
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
