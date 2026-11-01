/* eslint-disable no-undef */
// GC-015: actual forms, Chromium and disposable Flask API; no production data.
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
  const { vehicle, entry } = await page.evaluate(async () => {
    await window.gc015.auth.updateUser({ volume_unit: 'gallons_us', currency: 'GBP', language: 'en' })
    const api = window.gc015.api
    const vehicle = (await api.post('/vehicles', { name: 'Miles fixture', make: 'Test', model: 'Car', distance_unit: 'miles', fuel_type: 'petrol' })).data.vehicle
    const entry = (await api.post('/fuel', { vehicle_id: vehicle.id, date: '2026-01-02', odometer: 1000, liters: 37.85,
      price_per_liter: 1.321, total_price: 49.99, full_tank: true, currency: 'GBP', notes: 'Original' })).data.entry
    return { vehicle, entry }
  })
  for (const unit of ['gallons_us', 'gallons_uk']) {
    await page.evaluate(unit => window.gc015.auth.updateUser({ volume_unit: unit }), unit)
    for (let n = 0; n < 3; n++) {
      await go(`/vehicles/${vehicle.id}/fuel/add?edit=${entry.id}`)
      await page.locator('textarea[name="notes"]').waitFor()
      assert.equal(await page.locator('input[name="total_cost"]').inputValue(), '49.99')
      await page.locator('textarea[name="notes"]').fill(`${unit} note ${n}`)
      const [response] = await Promise.all([
        page.waitForResponse(r => r.url().endsWith(`/api/fuel/${entry.id}`) && r.request().method() === 'PUT'),
        page.getByRole('button', { name: 'Save', exact: true }).click(),
      ]).catch(async error => {
        console.log(await page.locator('form').evaluate(form => ({ text: form.innerText, inputs: [...form.elements].map(e => ({ name: e.name, value: e.value, error: e.validationMessage })) })))
        await page.screenshot({ path: join(output, 'form-failure.png') })
        throw error
      })
      assert.equal(response.status(), 200)
      const stored = await page.evaluate(async id => (await window.gc015.api.get(`/fuel/${id}`)).data, entry.id)
      for (const field of ['liters', 'price_per_liter', 'total_price', 'amount', 'odometer']) assert.equal(stored[field], entry[field], field)
    }
    results.push(`${unit}: three notes-only saves preserved all original measurements and cost`)
  }
  await go(`/vehicles/${vehicle.id}/edit`)
  await page.getByText('Distance units cannot change while mileage, thresholds or history exist.').waitFor()
  assert.equal(await page.getByRole('button', { name: 'Miles', exact: true }).isDisabled(), true)
  assert.equal(await page.getByRole('button', { name: 'Kilometres', exact: true }).isDisabled(), true)
  await page.screenshot({ path: join(output, 'locked-distance.png') })
  results.push('History prevents a unit switch in the actual vehicle form')
  await go('/profile')
  const preference = page.locator('select[name="volume_unit"]')
  await preference.waitFor()
  assert.deepEqual(await preference.locator('option').evaluateAll(options => options.map(option => option.value)), ['liters', 'gallons_us', 'gallons_uk'])
  results.push('Profile offers explicit US and imperial gallons')
  await go('/backup')
  const source = page.getByLabel('Source fuel volume')
  await source.waitFor()
  const importButton = page.getByRole('button', { name: 'Select LubeLogger Backup (.zip)', exact: true })
  assert.equal(await importButton.isDisabled(), true)
  await source.selectOption('imperial_gallons')
  await page.getByLabel('Source odometer unit').selectOption('miles')
  assert.equal(await importButton.isDisabled(), false)
  await page.screenshot({ path: join(output, 'explicit-import-units.png') })
  if (process.env.GC_LUBELOG_FIXTURE) {
    const chooser = page.waitForEvent('filechooser')
    await importButton.click()
    const response = page.waitForResponse(r => r.url().endsWith('/api/backup/import/lubelog'))
    await (await chooser).setFiles(process.env.GC_LUBELOG_FIXTURE)
    const imported = await response
    assert.equal(imported.status(), 200, await imported.text())
    assert.ok((await imported.json()).preview.new_records > 0)
    const [applied] = await Promise.all([
      page.waitForResponse(r => r.url().endsWith('/api/backup/import/lubelog')),
      page.getByRole('button', { name: 'Apply import', exact: true }).click(),
    ])
    assert.equal(applied.status(), 200, await applied.text())
    const data = await applied.json()
    assert.equal(data.summary.unit_conversion.source_volume_unit, 'imperial_gallons')
    const fuel = await page.evaluate(async () => (await window.gc015.api.get('/fuel')).data.entries)
    const importedFuel = fuel.filter(row => row.vehicle_id !== vehicle.id)
    assert.equal(importedFuel.length, 2)
    for (const row of importedFuel) assert.equal(row.liters, 45.46)
    results.push('Real multipart LubeLogger import converts imperial gallons to litres')
  }
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ results, browserErrors: errors }, null, 2))
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
