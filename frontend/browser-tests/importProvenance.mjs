/* eslint-disable no-undef */
// GC-016: real import previews, explicit decisions and replay through Chromium.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc015/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/unitHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: req.headers }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') })
      req.pipe(proxy); return
    }
    res.setHeader('Cache-Control', 'no-store')
    if (req.url === '/harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    res.setHeader('Content-Type', 'text/html')
    res.end('<!doctype html><html><head><link rel="stylesheet" href="/style.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>')
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const errors = [], results = []
try {
  const context = await browser.newContext({ viewport: { width: 1200, height: 1000 } })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  page.on('dialog', dialog => dialog.accept())
  async function go(path) {
    await page.goto(origin + path)
    await page.waitForFunction(() => window.gc015 && !window.gc015.auth.isLoading)
  }
  await go('/login')
  await page.evaluate(() => window.gc015.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.gc015.auth.isAuthenticated)
  const vehicle = await page.evaluate(async () => (await window.gc015.api.post('/vehicles', { name: 'Import fixture' })).data.vehicle)
  await go('/backup')
  await page.getByRole('button', { name: 'Service', exact: true }).click()
  await page.getByLabel('Source label (optional)').fill('Browser garage')
  const makeCsv = amount => `source_id,vehicle_id,date,amount,title\n1,${vehicle.id},2026-01-01,${amount},Oil\n2,${vehicle.id},2026-01-01,50,Inspection\n`
  const rows = () => page.evaluate(async () => (await window.gc015.api.get('/services')).data.entries)
  const upload = async text => {
    const response = page.waitForResponse(r => r.url().endsWith('/api/backup/import/csv'))
    await page.locator('input[type="file"][accept=".csv"]').setInputFiles({ name: 'services.csv', mimeType: 'text/csv', buffer: Buffer.from(text) })
    const result = await response
    assert.equal(result.status(), 200, await result.text())
    await page.getByRole('heading', { name: 'Review import' }).waitFor()
    return (await result.json()).preview
  }
  const apply = async name => {
    const response = page.waitForResponse(r => r.url().endsWith('/api/backup/import/csv'))
    await page.getByRole('button', { name, exact: true }).click()
    const result = await response
    assert.equal(result.status(), 200, await result.text())
    await page.getByRole('heading', { name: 'Import completed', exact: true }).waitFor()
    return result.json()
  }
  assert.equal((await upload(makeCsv(50))).new_records, 2)
  assert.equal((await rows()).length, 0)
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  assert.equal((await rows()).length, 0)
  results.push('Preview and cancel leave all records unchanged')
  await upload(makeCsv(50))
  assert.equal((await apply('Apply import')).created, 2)
  assert.equal((await rows()).reduce((sum, row) => sum + row.amount, 0), 100)
  results.push('Two same-day, same-cost expenses remain distinct; total is 100')
  assert.equal((await upload(makeCsv(50))).exact_repeats, 2)
  assert.equal((await apply('Apply import')).created, 0)
  assert.equal((await rows()).length, 2)
  results.push('Repeating the file creates no expenses')
  assert.equal((await upload(makeCsv(75))).conflicts, 1)
  await page.screenshot({ path: join(output, 'source-conflict.png'), fullPage: true })
  await apply('Keep existing and import new records')
  assert.equal((await rows()).reduce((sum, row) => sum + row.amount, 0), 100)
  results.push('Changed source prompts for a decision and keep-existing preserves costs')
  await page.getByLabel('Source label (optional)').fill('Another garage')
  const separate = await upload(makeCsv(50))
  assert.equal(separate.new_records, 2)
  assert.equal(separate.possible_duplicates, 2)
  await apply('Apply import')
  assert.equal((await rows()).length, 4)
  results.push('Another source with the same IDs remains distinct; similarity is advisory')
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ results, browserErrors: errors }, null, 2))
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
