/* eslint-disable no-undef */
// GC-020: Chromium + real pages/forms + disposable browser_expense_fixture API.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc020/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/expenseHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
const requests = [], errors = [], results = []
let failDetails = false
const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      requests.push({ method: req.method, path: req.url })
      if (failDetails && req.url.includes('/expense-records')) {
        res.writeHead(503, { 'Content-Type': 'application/json' }); res.end('{"error":"Fixture failure"}'); return
      }
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method,
        path: req.url, headers: req.headers }, response => { res.writeHead(response.statusCode, response.headers); response.pipe(res) })
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
  const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } })
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(origin + '/login')
  await page.waitForFunction(() => window.gc020 && !window.gc020.auth.isLoading)
  await page.evaluate(() => window.gc020.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.gc020.auth.isAuthenticated)
  const go = async path => { await page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path) }
  const before = requests.length
  await go('/vehicles/1/expenses?year=2024')
  await page.getByText('Station 121', { exact: true }).waitFor()
  await page.getByText('Selected category, all pages: 1210.00 GBP', { exact: true }).waitFor()
  assert.equal(requests.slice(before).filter(r => r.path.includes('/expense-records')).length, 1)
  assert.equal(requests.slice(before).filter(r => r.path.includes('/expenses-summary')).length, 1)
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await page.getByText('Station 101', { exact: true }).waitFor()
  assert.match(page.url(), /page=2/)
  assert.equal(requests.slice(before).filter(r => r.path.includes('/expenses-summary')).length, 1)
  results.push('121 records: bounded requests, next page, unchanged complete totals')

  await page.getByRole('button', { name: /^January 2024: .* GBP$/ }).click()
  await page.getByText('Station 121', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await page.getByText('Station 101', { exact: true }).waitFor()
  const returnUrl = page.url()
  const beforeEdit = requests.length
  await page.getByTitle('Edit', { exact: true }).first().click()
  await page.locator('textarea[name="notes"]').fill('GC-020 edit return')
  const [saved] = await Promise.all([
    page.waitForResponse(r => r.request().method() === 'PUT' && /\/api\/fuel\/\d+$/.test(r.url())),
    page.getByRole('button', { name: 'Save', exact: true }).click(),
  ])
  assert.equal(saved.status(), 200)
  await page.getByText('Station 101', { exact: true }).waitFor()
  assert.equal(page.url(), returnUrl)
  assert.equal(requests.slice(beforeEdit).filter(r => r.method === 'GET' && /^\/api\/fuel\/\d+$/.test(r.path)).length, 1)
  await page.reload()
  await page.getByText('Station 101', { exact: true }).waitFor()
  assert.equal(page.url(), returnUrl)
  results.push('Actual fuel edit/save and reload preserve year/month/page filters')

  await go('/vehicles/1/charts?year=2024')
  await page.getByText('1386.00 GBP', { exact: true }).first().waitFor()
  const report = await page.evaluate(async () => (await window.gc020.api.post('/reports/preview',
    { vehicle_ids: [1], period: 'year', year: 2024 })).data)
  assert.equal(report.totals.grand_total, 1386)
  assert.equal(report.display_currency, 'GBP')
  await page.getByRole('link', { name: 'View records' }).click()
  await page.getByText('Station 121', { exact: true }).waitFor()
  assert.match(page.url(), /year=2024/)
  await page.getByRole('button', { name: 'Insurance', exact: true }).click()
  await page.getByText('Estimate for selected period: 96.00 GBP', { exact: true }).waitFor()
  await page.getByText('10.00 EUR', { exact: false }).first().waitFor()
  results.push('Charts, paginated table and report reconcile including EUR insurance estimates')

  await go('/vehicles/2/expenses?year=2024')
  await page.getByRole('option', { name: '2020', exact: true }).waitFor({ state: 'attached' })
  await page.getByRole('combobox').selectOption('2020')
  await page.getByRole('button', { name: 'Insurance', exact: true }).click()
  await page.getByText('Estimate for selected period: 20.00 GBP', { exact: true }).waitFor()
  results.push('Insurance-only history exposes older years and converted totals')

  failDetails = true
  await go('/vehicles/1/expenses?year=2024&tab=consumable')
  await page.getByText('Records could not be loaded. They are not shown as an empty list.', { exact: false }).waitFor()
  assert.equal(await page.getByText('No entries found', { exact: true }).count(), 0)
  failDetails = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByText('Tyres', { exact: true }).waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: join(output, 'expenses-mobile.png'), fullPage: true })
  results.push('Failed detail request is visible and retry restores records on mobile')
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, errors, requests }, null, 2))
  console.log(results.join('\n'))
} finally {
  await browser.close()
  await new Promise(resolve => server.close(resolve))
}
