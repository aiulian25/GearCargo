/* eslint-disable no-undef */
// GC-021: Chromium + real reminder forms, API and mocked transports.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc021/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/reminderHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
const requests = [], errors = [], results = []
const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      requests.push({ method: req.method, path: req.url })
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: { ...req.headers, 'x-gc021-fixture': 'disposable-browser-only' } }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') })
      req.pipe(proxy); return
    }
    res.setHeader('Cache-Control', 'no-store')
    if (req.url === '/harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    res.setHeader('Content-Type', 'text/html')
    res.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>')
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] })
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } })
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(origin + '/login')
  await page.waitForFunction(() => window.gc021 && !window.gc021.auth.isLoading)
  await page.evaluate(() => window.gc021.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.gc021.auth.isAuthenticated)
  const go = async path => { await page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path) }
  const tick = days => page.evaluate(async days => (await window.gc021.api.post('/__gc021/tick', { advance_days: days || 0 })).data, days)
  const get = id => page.evaluate(async id => (await window.gc021.api.get(`/reminders/${id}`)).data, id)
  assert.deepEqual((await tick()).sent, [])
  await go('/vehicles/1/reminder/add?edit=1')
  await page.getByRole('spinbutton', { name: 'Days before the due date' }).fill('7')
  await page.getByRole('checkbox', { name: 'Push notification' }).uncheck()
  await page.locator('[name="repeat_interval"]').selectOption('1_month')
  await page.locator('[name="repeat_mileage"]').fill('5000')
  const [saved] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/reminders/1') && r.request().method() === 'PUT'),
    page.getByRole('button', { name: 'Save', exact: true }).click(),
  ])
  assert.equal(saved.status(), 200)
  const stored = await get(1)
  assert.equal(stored.notify_days_before, 7)
  assert.equal(stored.repeat_mileage, 5000)
  assert.equal(stored.notify_push, false)
  assert.equal(stored.notify_email, true)
  await tick()
  assert.deepEqual((await tick()).sent, [{ channel: 'email', title: 'Lead reminder' }])
  results.push('Actual edit form preserves lead time, mileage interval and channel choices; two ticks send one email')

  await go('/reminders')
  const leadCard = page.getByRole('link').filter({ has: page.getByText('Lead reminder', { exact: true }) })
  await leadCard.getByTitle('Snooze 7 days', { exact: true }).click()
  await page.waitForResponse(r => r.url().includes('/api/reminders?') && r.request().method() === 'GET')
  assert.equal((await get(1)).due_date, '2028-02-29')
  assert.equal((await tick(6)).sent.length, 1)
  assert.equal((await tick(1)).sent.length, 2)
  assert.equal((await tick()).sent.length, 2)
  results.push('Snooze leaves the due date intact, suppresses delivery until expiry, then sends once')

  await go('/vehicles/1')
  await go('/reminders')
  page.once('dialog', async dialog => {
    assert.match(dialog.message(), /at least 12001/)
    assert.match(dialog.message(), /miles/)
    await dialog.accept('17000')
  })
  const legacy = page.getByRole('link').filter({ has: page.getByText('Legacy mileage', { exact: true }) })
  const [completed] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/reminders/2/complete') && r.status() === 200),
    legacy.getByTitle('Mark complete', { exact: true }).click(),
  ])
  assert.equal((await completed.json()).reminder.completed, true)
  const rows = await page.evaluate(async () => (await window.gc021.api.get('/reminders', { params: { vehicle_id: 1 } })).data.reminders)
  const successor = rows.find(row => row.title === 'Legacy mileage' && row.id !== 2)
  assert.equal(successor.due_mileage, 17000)
  results.push('Legacy mileage completion requires an explicit threshold and creates one meaningful successor')

  await go('/vehicles/1/reminder/add?edit=1')
  await page.getByRole('spinbutton', { name: 'Days before the due date' }).waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: join(output, 'reminder-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, errors, requests }, null, 2))
  console.log(results.join('\n'))
} finally {
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
