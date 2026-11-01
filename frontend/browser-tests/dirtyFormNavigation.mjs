/* global process, URL, console, window, navigator, CustomEvent */
// GC-031: production app/router/worker with a local fixture API. No production data.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc031/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
await mkdir(output, { recursive: true })
let saveMode = 'success', account = 1
const records = []
const vehicle = { id: 1, name: 'Navigation fixture', make: 'Fixture', model: 'Car', year: 2026, revision: 1, distance_unit: 'km', current_mileage: 100 }
const user = () => ({ id: account, username: `Account ${account}`, name: `Account ${account}`, email: `account${account}@example.invalid`, currency: 'GBP', language: 'en', date_format: 'DD/MM/YYYY', timezone: 'Europe/London', volume_unit: 'liters' })
const identity = () => ({ owner_id: account, owner_key: String(account).repeat(64), generation: 'a'.repeat(64) })
const entry = { id: 5, revision: 1, date: '2026-01-01', odometer: 100, liters: 10, price_per_liter: 2, total_price: 20, currency: 'GBP', notes: 'Original note', station: 'Fixture station', full_tank: true, attachments: [] }
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost')
    if (url.pathname.startsWith('/api/')) {
      res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store')
      let body = ''; for await (const chunk of req) body += chunk
      if (req.method === 'PUT' || req.method === 'POST') records.push({ path: url.pathname, method: req.method, body })
      if (url.pathname === '/api/auth/me') { res.end(JSON.stringify(user())); return }
      if (url.pathname === '/api/auth/offline-identity') { res.end(JSON.stringify(identity())); return }
      if (url.pathname === '/api/auth/csrf-token') { res.end(JSON.stringify({ csrf_token: 'fixture-csrf' })); return }
      if (url.pathname === '/api/auth/login') { account = 2; res.end(JSON.stringify({ user: user() })); return }
      if (url.pathname === '/api/vehicles/1' && req.method === 'GET') { res.end(JSON.stringify(vehicle)); return }
      if (url.pathname === '/api/vehicles') { res.end(JSON.stringify({ vehicles: [vehicle] })); return }
      if (url.pathname === '/api/fuel/5' && req.method === 'GET') { res.end(JSON.stringify(entry)); return }
      if (url.pathname === '/api/fuel/5' && req.method === 'PUT' || url.pathname === '/api/vehicles/1' && req.method === 'PUT') {
        if (saveMode === 'fail') { res.statusCode = 400; res.end(JSON.stringify({ error: 'Fixture save rejected' })); return }
        res.end(JSON.stringify({ vehicle: { ...vehicle, revision: 2 }, entry: { ...entry, revision: 2 } })); return
      }
      if (url.pathname.endsWith('/expenses-summary')) { res.end(JSON.stringify({ display_currency: 'GBP', converted: true, as_of: '2026-12-31', available_years: [2026], totals: { fuel: 20, grand_total: 20 }, monthly: [{ month: '2026-01', total: 20, breakdown: { fuel: 20 } }] })); return }
      if (url.pathname.endsWith('/expense-records')) { res.end(JSON.stringify({ category: 'fuel', records: [entry], total: 1, pages: 1, current_page: 1, per_page: 20, display_currency: 'GBP', page_total: 20 })); return }
      if (url.pathname === '/api/push/vapid-key') { res.end(JSON.stringify({ enabled: false })); return }
      res.end(JSON.stringify({ entries: [], reminders: [], events: [], policies: [], todos: [], fines: [], data: [], notifications: [] })); return
    }
    const path = url.pathname, suffix = extname(path)
    const file = join(root, 'dist', !suffix ? 'index.html' : path)
    res.setHeader('Content-Type', ({ '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml', '.png': 'image/png' })[extname(file)] || 'application/octet-stream')
    res.setHeader('Cache-Control', 'no-store'); res.end(await readFile(file))
  } catch (error) { res.statusCode = 404; res.end(String(error)) }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM, args: ['--no-sandbox', '--disable-dev-shm-usage'] })
const results = [], errors = []
const record = value => { results.push(value); console.log(value) }
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage(); page.setDefaultTimeout(10000); page.setDefaultNavigationTimeout(15000); page.on('pageerror', error => errors.push(error.message))
  await page.goto(origin + '/vehicles')
  await page.getByRole('heading', { name: 'My Vehicles', exact: true }).waitFor()
  await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  // Re-enter after worker activation so auth binds its private client lease.
  await page.reload()
  await page.locator('a[href="/vehicles/1"]').click()
  await page.getByRole('heading', { name: 'Navigation fixture', exact: true }).locator('../..').locator('button.btn-icon').last().click()
  await page.getByRole('link', { name: 'Edit Vehicle', exact: true }).click()
  const name = page.locator('[name="name"]'); await name.waitFor(); await name.fill('Keep my changes')
  const close = page.getByRole('button', { name: 'Close', exact: true })
  const dialog = page.getByRole('dialog', { name: 'Unsaved changes' })
  const stay = () => page.getByRole('button', { name: 'Keep editing', exact: true }).click()
  const discard = () => page.getByRole('button', { name: 'Discard changes', exact: true }).click()
  await close.click(); await dialog.waitFor(); await stay(); assert.equal(await name.inputValue(), 'Keep my changes')
  await page.getByRole('link', { name: 'Calendar', exact: true }).click(); await dialog.waitFor()
  await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'hidden' }); assert.equal(await name.inputValue(), 'Keep my changes')
  // Native browser history, not router.navigate(-1).
  await page.evaluate(() => window.history.back()); await dialog.waitFor(); await stay()
  assert.equal(await name.inputValue(), 'Keep my changes'); assert.equal(new URL(page.url()).pathname, '/vehicles/1/edit')
  const reloadPrompt = page.waitForEvent('dialog')
  const reloading = page.reload({ timeout: 5000 }).catch(() => null)
  const nativeDialog = await reloadPrompt; assert.equal(nativeDialog.type(), 'beforeunload'); await nativeDialog.dismiss(); await reloading
  assert.equal(await name.inputValue(), 'Keep my changes')
  record('Close, app navigation, native browser Back and canceled reload retain typed values on Stay/Escape')
  await page.evaluate(() => window.history.back()); await dialog.waitFor(); await discard(); await page.waitForURL('**/vehicles/1')
  await page.evaluate(() => window.history.forward()); await name.waitFor(); assert.equal(await name.inputValue(), 'Navigation fixture')
  record('Discard proceeds to the original history target; Forward starts with saved values')
  await name.fill('Failed save stays')
  saveMode = 'fail'; await page.getByRole('button', { name: 'Save', exact: true }).click(); await page.getByText('Fixture save rejected', { exact: true }).waitFor()
  await close.click(); await dialog.waitFor(); await stay(); assert.equal(await name.inputValue(), 'Failed save stays')
  saveMode = 'success'
  await page.getByRole('button', { name: 'Save', exact: true }).click(); await page.waitForURL('**/vehicles/1')
  assert.equal(await dialog.count(), 0); results.push('Failed server save retains protection; successful save exits without another confirmation')

  // Warm the expense destination and open its edit link through the actual UI.
  const expense = '/vehicles/1/expenses?year=2026&month=1&category=fuel&page=1'
  await page.goto(origin + expense); await page.getByText('Fixture station', { exact: true }).waitFor()
  const edit = page.getByRole('button', { name: 'Edit', exact: true }).first(); await edit.click()
  const notes = page.locator('[name="notes"]'); await notes.waitFor(); await notes.fill('Durable offline note')
  await context.setOffline(true)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.waitForURL(url => url.pathname === '/vehicles/1/expenses')
  assert.equal(new URL(page.url()).search, new URL(origin + expense).search)
  assert.equal(await dialog.count(), 0)
  const queued = await page.evaluate(async () => {
    const databases = await window.indexedDB.databases()
    const database = databases.find(db => db.name?.toLowerCase().includes('mutation'))
    if (!database) return { databases }
    return new Promise((resolve, reject) => {
      const request = window.indexedDB.open(database.name)
      request.onerror = () => reject(request.error)
      request.onsuccess = () => {
        const db = request.result, read = db.transaction('pending').objectStore('pending').getAll()
        read.onsuccess = () => { resolve(read.result); db.close() }; read.onerror = () => reject(read.error)
      }
    })
  })
  assert.ok(JSON.stringify(queued).includes('Durable offline note'), JSON.stringify(queued))
  await writeFile(join(output, 'offline-queue.json'), JSON.stringify(queued, null, 2))
  record('Real production worker durably queues the offline edit; save returns to identical expense filters without prompting')
  await context.setOffline(false)

  await page.goto(origin + '/vehicles/1/edit'); await name.waitFor(); await name.fill('Private account A draft')
  await page.getByRole('link', { name: 'Calendar', exact: true }).click(); await dialog.waitFor()
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('private-identity-suspended')))
  await page.waitForURL('**/login'); await dialog.waitFor({ state: 'hidden' })
  assert.equal(await page.getByText('Private account A draft').count(), 0)
  record('Forced account/session boundary dismisses the dialog, removes private form state and reaches sign-in')
  // A new login goes through the real AuthProvider/private-storage boundary.
  await page.locator('input[name="email"]').fill('account2@example.invalid')
  await page.locator('input[type="password"]').fill('FixturePassword123!')
  await page.getByRole('button', { name: 'SIGN IN', exact: true }).click()
  await page.waitForURL(origin + '/')
  await page.goto(origin + '/vehicles/1/edit'); await name.waitFor(); assert.equal(await name.inputValue(), 'Navigation fixture')
  record('Account B does not inherit account A form values')

  // Mobile viewport, real touch targets and modal focus/escape behavior.
  await page.setViewportSize({ width: 390, height: 844 }); await name.fill('Mobile draft')
  await page.getByRole('link', { name: 'Calendar', exact: true }).click(); await dialog.waitFor(); await page.screenshot({ path: join(output, 'mobile-discard-dialog.png'), fullPage: true })
  await page.keyboard.press('Tab'); assert.equal(await page.getByRole('button', { name: 'Discard changes', exact: true }).evaluate(el => el === window.document.activeElement), true)
  await page.keyboard.press('Tab'); assert.equal(await page.getByRole('button', { name: 'Keep editing', exact: true }).evaluate(el => el === window.document.activeElement), true)
  await page.keyboard.press('Escape'); assert.equal(await name.inputValue(), 'Mobile draft')
  record('Mobile dialog remains readable; Tab stays in the dialog and Escape preserves edits')
  await page.locator('header button').filter({ hasText: 'Account 2' }).click()
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click(); await dialog.waitFor(); await stay()
  assert.equal(await name.inputValue(), 'Mobile draft')
  await page.locator('header button').filter({ hasText: 'Account 2' }).click()
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click(); await dialog.waitFor(); await discard()
  await page.waitForURL('**/login'); assert.equal(await dialog.count(), 0)
  record('Explicit sign-out asks before clearing private state; Stay retains the form and Discard signs out without a second prompt')
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, errors, records }, null, 2))
  console.log(results.join('\n'))
} catch (error) {
  for (const context of browser.contexts()) for (const page of context.pages()) {
    await page.screenshot({ path: join(output, 'failure.png'), fullPage: true }).catch(() => {})
    await writeFile(join(output, 'failure.txt'), await page.locator('body').innerText()).catch(() => {})
  }
  console.error({ results, errors }); throw error
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
