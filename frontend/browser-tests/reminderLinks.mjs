/* eslint-disable no-undef */
// GC-022: built App/router + built worker handlers + real Flask API.
// Notification display/open/focus use adapters: no OS notification is sent.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc022/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
await mkdir(output, { recursive: true })
const requests = [], errors = [], results = []
const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      requests.push({ method: req.method, path: req.url })
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: { ...req.headers, 'x-gc022-fixture': 'disposable-browser-only' } }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') })
      req.pipe(proxy); return
    }
    const path = req.url.split('?')[0]
    const types = { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.webmanifest': 'application/manifest+json' }
    let body, file = join(root, 'dist', path === '/' ? 'index.html' : path)
    try { body = await readFile(file) }
    catch { if (extname(path)) throw new Error('Missing asset'); file = join(root, 'dist/index.html'); body = await readFile(file) }
    if (path === '/sw.js') body = `self.__gc022handlers = {}; const add = self.addEventListener.bind(self); self.addEventListener = (name, callback, ...rest) => { if (['push', 'notificationclick'].includes(name)) self.__gc022handlers[name] = callback; return add(name, callback, ...rest); };\n` + body
    res.setHeader('Content-Type', types[extname(file)] || 'application/octet-stream')
    res.setHeader('Cache-Control', 'no-store')
    res.end(body)
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] })
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } })
  context.on('page', page => page.on('pageerror', error => errors.push(error.message)))
  let page = await context.newPage()
  await page.goto(origin + '/reminders/1')
  await page.waitForURL('**/login?reminder=1')
  async function login(page, account = 'a') {
    // Session expiry can navigate through both the auth guard and interceptor.
    await page.waitForLoadState('networkidle')
    await page.locator('[name="email"]').fill(`queue-${account}@example.invalid`)
    await page.locator('[name="password"]').fill('BrowserFixture123!')
    await page.locator('button[type="submit"]').click()
  }
  await login(page)
  await page.getByRole('heading', { name: 'Date notification reminder', exact: true }).waitFor()
  assert.equal(new URL(page.url()).pathname, '/reminders/1')
  assert.equal(await page.getByRole('link', { name: 'Notification vehicle', exact: true }).getAttribute('href'), '/vehicles/1')
  results.push('A signed-out legacy notification URL returns to its reminder after real sign-in')
  const payloads = await page.evaluate(async () => (await fetch('/api/__gc022/payloads')).json())
  await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  const worker = context.serviceWorkers()[0]
  assert.ok(worker)
  async function click(payload) {
    const decision = await worker.evaluate(async payload => {
      let pending, displayed, result
      Object.defineProperty(self.registration, 'showNotification', { configurable: true, value: async (title, options) => { displayed = { title, ...options } } })
      self.__gc022handlers.push({ data: { json: () => payload }, waitUntil: promise => { pending = promise } })
      await pending
      delete self.registration.showNotification
      const actualClients = self.clients
      const clientsDescriptor = Object.getOwnPropertyDescriptor(self, 'clients')
      Object.defineProperty(self, 'clients', { configurable: true, value: {
        matchAll: async options => (await actualClients.matchAll(options)).map(client => ({ url: client.url,
          focus: async () => { result = { action: 'focus', url: client.url } } })),
        openWindow: async url => { result = { action: 'open', url } },
      } })
      try {
        self.__gc022handlers.notificationclick({ notification: { data: displayed.data, close() {} }, waitUntil: promise => { pending = promise } })
        await pending
      } finally {
        if (clientsDescriptor) Object.defineProperty(self, 'clients', clientsDescriptor)
        else delete self.clients
      }
      return { ...result, target: displayed.data.url }
    }, payload)
    assert.equal(decision.target, payload.data.url)
    let target
    if (decision.action === 'open') { target = await context.newPage(); await target.goto(origin + decision.url) }
    else { target = context.pages().find(p => p.url() === decision.url); await target.bringToFront() }
    await target.getByRole('heading', { name: payload.title.replace('Reminder: ', ''), exact: true }).waitFor()
    assert.equal(new URL(target.url()).pathname, payload.data.url)
    assert.equal(await target.getByRole('link', { name: 'Notification vehicle', exact: true }).getAttribute('href'), '/vehicles/1')
    assert.ok(await target.getByText('12,000 miles', { exact: true }).count())
    return { page: target, action: decision.action }
  }
  for (const payload of payloads) {
    for (const open of context.pages()) await open.close()
    const closed = await click(payload)
    assert.equal(closed.action, 'open')
    const count = context.pages().length
    const existing = await click(payload)
    assert.equal(existing.action, 'focus')
    assert.equal(context.pages().length, count)
    page = existing.page
    results.push(`${payload.data.type}: closed app opens exact reminder; existing matching window focuses without duplication`)
  }
  await page.getByRole('button', { name: 'Snooze 7 days', exact: true }).click()
  await page.getByText('Notifications snoozed until', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Mark complete', exact: true }).click()
  await page.getByText('Completed', { exact: true }).waitFor()
  await page.reload()
  await page.getByText('Completed', { exact: true }).waitFor()
  results.push('The focused detail supports snooze/completion and keeps completed records accessible after reload')
  await page.goto(origin + '/reminders/999999')
  await page.getByRole('alert').filter({ hasText: 'This reminder is unavailable.' }).waitFor()
  assert.equal(await page.getByRole('link', { name: 'All reminders', exact: true }).getAttribute('href'), '/reminders')
  results.push('A missing/deleted ID shows an unavailable state with a reminder-list backlink')

  await context.clearCookies()
  await page.goto(origin + '/reminders/1')
  await page.waitForURL('**/login?reminder=1')
  await login(page, 'b')
  await page.getByRole('alert').filter({ hasText: 'This reminder is unavailable.' }).waitFor()
  assert.equal(await page.getByText('Private maintenance details', { exact: true }).count(), 0)
  assert.equal(await page.getByText('Date notification reminder', { exact: true }).count(), 0)
  results.push('An expired session preserves the target; a different account cannot read its title or details')
  await context.clearCookies()
  await page.goto(origin + '/reminders/1')
  await page.waitForURL('**/login?reminder=1')
  await login(page)
  await page.getByRole('heading', { name: 'Date notification reminder', exact: true }).waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: join(output, 'reminder-detail-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, errors, requests }, null, 2))
  console.log(results.join('\n'))
} finally {
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
