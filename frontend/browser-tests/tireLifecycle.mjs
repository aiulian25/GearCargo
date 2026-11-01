/* eslint-disable no-undef */
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-tires-proposal3/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/tireHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
let blockReadings = false
const errors = []
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/api/auth/tire-test') {
      res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><div id="root"></div><script type="module" src="/__tire-harness.js"></script>'); return
    }
    if (req.url === '/__tire-harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    if (req.url.startsWith('/api/')) {
      if (blockReadings && req.method === 'POST' && req.url.endsWith('/readings')) { req.socket.destroy(); return }
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
    await page.goto(origin + '/api/auth/tire-test')
    await page.waitForFunction(() => window.tireFixture && !window.tireFixture.auth.isLoading)
    await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
    await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  }
  const until = async check => {
    const deadline = Date.now() + 45000
    while (!(await check())) {
      if (Date.now() > deadline) throw new Error('Timed out waiting for committed offline reading')
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
  await page.evaluate(() => window.tireFixture.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.tireFixture.auth.isAuthenticated)
  await go('/vehicles/1/tires')
  await page.getByRole('button', { name: 'Add set' }).click()
  await page.getByLabel('Set name').fill('Summer wheels')
  await page.getByLabel('Link existing purchase').selectOption('1')
  await page.getByLabel('Rotation interval').fill('1000')
  await page.getByLabel('Your tread alert threshold').fill('3')
  await save('/api/tire-sets')
  await page.getByRole('button', { name: 'Install', exact: true }).click()
  await page.getByLabel('Measured/event date').fill('2026-01-01')
  await page.getByLabel('Odometer', { exact: true }).fill('1000')
  await save('/api/tire-sets/1/events')
  await page.getByRole('button', { name: 'Rotate', exact: true }).click()
  await page.getByLabel('Measured/event date').fill('2026-02-01')
  await page.getByLabel('Odometer', { exact: true }).fill('1500')
  await page.getByLabel('Front left', { exact: true }).selectOption('C')
  await page.getByLabel('Rear left', { exact: true }).selectOption('A')
  await save('/api/tire-sets/1/events')
  await page.getByRole('button', { name: 'Remove and store', exact: true }).click()
  await page.getByLabel('Measured/event date').fill('2026-03-01')
  await page.getByLabel('Odometer', { exact: true }).fill('2000')
  await save('/api/tire-sets/1/events')
  const savedSet = await page.evaluate(async () => (await window.tireFixture.api.get('/tire-sets/1')).data)
  assert.equal(savedSet.distance, 1000); assert.equal(savedSet.installed, false); assert.equal(savedSet.positions.FL, 'C')
  assert.equal(savedSet.purchase_entry_id, 1)
  await page.getByRole('button', { name: 'Add tread reading' }).click()
  await page.getByLabel('Measured tread depth').fill('4')
  await page.getByLabel('Measurement unit', { exact: true }).selectOption('32nds')
  blockReadings = true
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('form').waitFor({ state: 'detached' })
  await until(() => page.evaluate(async () => (await window.tireFixture.mutationDb.pending.count()) === 1))
  await page.close(); page = await context.newPage(); await open()
  assert.equal(await page.evaluate(() => window.tireFixture.mutationDb.pending.count()), 1)
  blockReadings = false
  await until(() => page.evaluate(async () => {
    const channel = new MessageChannel()
    await new Promise((resolve, reject) => { channel.port1.onmessage = e => e.data?.error ? reject(new Error(e.data.error)) : resolve(e.data); navigator.serviceWorker.controller.postMessage({ type: 'FORCE_SYNC' }, [channel.port2]) })
    return (await window.tireFixture.api.get('/tire-sets/1')).data.readings.length === 1
  }))
  assert.equal(await page.evaluate(() => window.tireFixture.mutationDb.pending.count()), 0)
  await go('/vehicles/1/tires')
  await page.getByRole('heading', { name: 'Summer wheels' }).waitFor()
  await page.getByText('Tread history by tire', { exact: true }).click()
  await page.getByText(/4 32nds of an inch/).waitFor({ timeout: 10000 })
  await page.screenshot({ path: join(output, 'desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false)
  await page.screenshot({ path: join(output, 'mobile.png'), fullPage: true })
  await page.getByRole('link', { name: 'Create maintenance reminder' }).click()
  await page.waitForFunction(() => document.querySelector('[name="reminder_type"]')?.value === 'tire_rotation')
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ passed: ['create/link existing purchase', 'install/rotate/remove through real forms', 'stable identities and 1000 km seasonal distance', 'offline reading survives tab restart and replays once', 'desktop/mobile no overflow', 'prefilled rotation reminder'], browserErrors: errors }, null, 2))
  console.log('6 browser acceptance checks passed')
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
