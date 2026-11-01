/* global process, URL, setTimeout, document, localStorage, console, getComputedStyle, location, NodeFilter, innerWidth, window */
// GC-030: actual pages, native keyboard/touch interaction, contrast and AT-SPI/Orca support.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve, join } from 'node:path'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc030/browser')
const require = createRequire(join(root, 'package.json'))
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const screenReader = process.env.GC_SCREEN_READER === '1'
const before = process.env.GC_BEFORE === '1'
const themes = process.env.GC_THEME ? [process.env.GC_THEME] : ['dark', 'light']
await mkdir(output, { recursive: true })
const { translations } = await import(join(root, 'src/i18n/translations.js'))
const exports = [...(await readFile(join(root, 'src/services/api.js'), 'utf8')).matchAll(/export const (\w+)/g)].map(m => m[1])
const fixtureApi = `
const get=async path=>({data:await(await fetch('/api'+path)).json()});
const basic={getAll:()=>Promise.resolve({data:{entries:[],policies:[],reminders:[],todos:[],fines:[]}})};
${exports.map(name => `export const ${name}=${name === 'vehicleApi' ? `{getById:id=>get('/vehicles/'+id),getExpenseSummary:(id,p)=>get('/vehicles/'+id+'/expenses-summary?'+new URLSearchParams(p)),getExpenseRecords:(id,p)=>get('/vehicles/'+id+'/expense-records?'+new URLSearchParams(p))}` : '{...basic}'};`).join('\n')}
export default {get,put:()=>Promise.resolve({data:{}})};`
await require('esbuild').build({ stdin: { contents: `
import React from 'react';import{createRoot}from'react-dom/client';import{BrowserRouter,Routes,Route,Link}from'react-router-dom';
import{LanguageProvider,useTranslation}from'./src/contexts/LanguageContext';import{DateFormatProvider}from'./src/contexts/DateFormatContext';
import VehicleExpenses from'./src/pages/vehicles/VehicleExpenses';import EditVehicle from'./src/pages/vehicles/EditVehicle';
function Harness(){const{language}=useTranslation();return <DateFormatProvider language={language}><Routes>
<Route path="/vehicles/:id/expenses" element={<VehicleExpenses/>}/><Route path="/vehicles/:id/edit" element={<EditVehicle/>}/>
<Route path="/vehicles/:id" element={<Link to="/vehicles/1/edit">Edit fixture vehicle</Link>}/></Routes></DateFormatProvider>}
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><Harness/></LanguageProvider></BrowserRouter>);
`, resolveDir: root, loader: 'jsx' }, bundle: true, outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'import.meta.env': '{}', 'process.env.NODE_ENV': '"production"' }, plugins: [{ name: 'fixture-transport', setup(build) {
    build.onResolve({ filter: /services\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    build.onResolve({ filter: /contexts\/AuthContext$/ }, () => ({ path: 'auth', namespace: 'fixture' }))
    build.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ contents: args.path === 'api' ? fixtureApi :
      "export const useAuth=()=>({user:{currency:'USD',volume_unit:'liters'}})", loader: 'jsx', resolveDir: root }))
  } }] })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
const requests = [], results = [], errors = [], contrastResults = []
const summary = { display_currency: 'GBP', as_of: '2026-12-31', converted: true, totals: { fuel: 1272, grand_total: 1272 },
  monthly: [{ month: '2026-01', total: 1234.5, breakdown: { fuel: 1234.5 } }, { month: '2026-02', total: 37.5, breakdown: { fuel: 37.5 } }], available_years: [2026] }
const records = [{ id: 1, date: '2026-01-01', station: 'January fuel', total_price: 1234.5, currency: 'GBP', attachments: [] },
  { id: 2, date: '2026-02-01', station: 'February fuel', total_price: 37.5, currency: 'GBP', attachments: [] }]
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost')
    if (url.pathname.startsWith('/api/')) {
      requests.push(url.pathname + url.search); res.setHeader('Content-Type', 'application/json')
      if (url.pathname === '/api/vehicles/1') {
        await new Promise(resolve => setTimeout(resolve, 250))
        res.end(JSON.stringify({ id: 1, name: 'Accessible car', revision: 1, distance_unit: 'km', make: 'Fixture', model: 'Car', year: 2026, photo_url: '/photo.svg' })); return
      }
      if (url.pathname.endsWith('/expenses-summary')) { res.end(JSON.stringify(summary)); return }
      if (url.pathname.endsWith('/expense-records')) {
        const month = Number(url.searchParams.get('month'))
        const rows = month ? records.filter(row => Number(row.date.slice(5, 7)) === month) : records
        res.end(JSON.stringify({ category: 'fuel', records: rows, current_page: 1, pages: 1, total: rows.length, per_page: 20,
          display_currency: 'GBP', page_total: rows.reduce((n, row) => n + row.total_price, 0), converted: true })); return
      }
      res.end('{}'); return
    }
    if (url.pathname === '/harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (url.pathname === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    if (url.pathname === '/photo.svg') { res.setHeader('Content-Type', 'image/svg+xml'); res.end('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="#64748b"/></svg>'); return }
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"></head><body><div id="root"></div><script type="module" src="/harness.js"></script></body></html>')
  } catch (error) { res.statusCode = 500; res.end(error.message) }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({ headless: !screenReader, executablePath: process.env.GC_CHROMIUM || undefined,
  args: ['--no-sandbox', '--disable-dev-shm-usage', ...(screenReader ? ['--force-renderer-accessibility'] : [])] })
const origin = `http://127.0.0.1:${server.address().port}`
const press = async (page, key) => {
  if (screenReader && process.env.GC_READER_KEYS) execFileSync('/usr/bin/python3', [process.env.GC_READER_KEYS, key])
  else await page.keyboard.press(key)
}
const pauseForReader = async page => { if (screenReader) await page.waitForTimeout(500) }
try {
  for (const theme of themes) for (const language of screenReader || before ? ['en'] : ['en', 'ro', 'es']) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, locale: language })
    await context.addInitScript(({ theme, language }) => { document.addEventListener('DOMContentLoaded', () => document.documentElement.classList.toggle('light', theme === 'light')); localStorage.setItem('language', language) }, { theme, language })
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message))
    if (screenReader && process.env.GC_READER_EDIT_ONLY === '1') {
      await page.goto(origin + '/vehicles/1'); await page.getByText('Edit fixture vehicle').waitFor()
      await page.bringToFront(); await page.waitForTimeout(2000)
      await page.getByText('Edit fixture vehicle').focus(); await pauseForReader(page); await press(page, 'Enter')
      const close = page.getByRole('button', { name: 'Close', exact: true })
      const remove = page.getByRole('button', { name: 'Remove vehicle photo', exact: true })
      await remove.waitFor(); await page.bringToFront(); await page.waitForTimeout(2000)
      await close.focus(); await page.waitForTimeout(1000)
      await remove.focus(); await page.waitForTimeout(1000)
      await press(page, 'Space'); await pauseForReader(page); assert.equal(await remove.count(), 0)
      await close.focus(); await page.waitForTimeout(1000)
      await press(page, 'Enter'); await page.getByText('Edit fixture vehicle').waitFor()
      results.push(`${theme}: Orca edit close/remove-photo focus and activation`)
      await context.close(); continue
    }
    await page.goto(origin + '/vehicles/1/expenses?year=2026')
    await page.getByText('January fuel', { exact: true }).waitFor()
    if (screenReader) { await page.bringToFront(); await page.waitForTimeout(1500) }
    const t = key => key.split('.').reduce((v, k) => v?.[k], translations[language])
    const names = Array.from({ length: 12 }, (_, i) => new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : language, { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2026, i, 1))))
    const label = i => `${names[i]} 2026: ${new Intl.NumberFormat(language, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(i === 0 ? 1234.5 : i === 1 ? 37.5 : 0)} GBP`
    const year = page.getByRole('combobox', { name: t('expenses.selectYear') })
    await year.focus(); await pauseForReader(page); await press(page, 'Tab'); await pauseForReader(page)
    if (before) {
      const oldMonth = page.getByRole('button', { name: names[0], exact: true })
      assert.equal(await oldMonth.evaluate(el => el.tagName), 'DIV')
      assert.equal(await oldMonth.evaluate(el => el === document.activeElement), false)
      console.log(`Original regression reproduced (${theme}): Tab skips January; its element is a DIV.`)
      await context.close(); continue
    }
    for (let i = 0; i < 12; i++) {
      const button = page.getByRole('button', { name: label(i), exact: true })
      assert.equal(await button.evaluate(el => el === document.activeElement), true, `Tab order ${language}/${theme}/${names[i]}`)
      assert.equal(await button.evaluate(el => el.tagName), 'BUTTON')
      const focus = await button.evaluate(el => ({ width: getComputedStyle(el).outlineWidth, style: getComputedStyle(el).outlineStyle, visible: el.matches(':focus-visible') }))
      assert.equal(focus.visible, true); assert.ok(parseFloat(focus.width) >= 2 && focus.style !== 'none')
      await press(page, i % 2 ? 'Space' : 'Enter'); await pauseForReader(page)
      await page.waitForFunction(month => new URL(location.href).searchParams.get('month') === String(month), i + 1)
      await page.waitForFunction(label => Array.from(document.querySelectorAll('button')).find(el => el.getAttribute('aria-label') === label)?.getAttribute('aria-pressed') === 'true', label(i))
      await press(page, 'Tab'); await pauseForReader(page)
    }
    const clear = page.getByRole('button', { name: t('expenses.fullYear'), exact: true })
    assert.equal(await clear.evaluate(el => el === document.activeElement), true)
    await press(page, 'Space'); await pauseForReader(page)
    await page.getByText('January fuel', { exact: true }).waitFor(); await page.getByText('February fuel', { exact: true }).waitFor()
    assert.equal(new URL(page.url()).searchParams.has('month'), false)
    assert.equal(await clear.evaluate(el => el === document.activeElement), true)
    assert.equal(await clear.getAttribute('aria-pressed'), 'true')
    // The same focused month also toggles back to the full year.
    const january = page.getByRole('button', { name: label(0), exact: true })
    await january.focus(); await pauseForReader(page); await press(page, 'Enter'); await pauseForReader(page)
    await page.getByText('January fuel', { exact: true }).waitFor()
    await page.waitForFunction(() => !document.body.textContent.includes('February fuel'))
    await press(page, 'Space'); await pauseForReader(page)
    await page.getByText('February fuel', { exact: true }).waitFor()
    await clear.focus(); await pauseForReader(page); await press(page, 'Tab'); await pauseForReader(page)
    const details = page.locator('summary', { hasText: t('expenses.monthlyTotals') })
    assert.equal(await details.evaluate(el => el === document.activeElement), true)
    await press(page, 'Enter'); await pauseForReader(page)
    const table = page.getByRole('table', { name: t('expenses.monthlyTotalsYear').replace('{year}', 2026) })
    await table.waitFor(); assert.equal(await table.getByRole('row').count(), 13)
    if (screenReader && process.env.GC_READER_KEYS) {
      // Switch Orca to browse mode, reach the native table and read its rows.
      await press(page, 'Insert+a'); await pauseForReader(page)
      await press(page, 't'); await pauseForReader(page)
      for (let i = 0; i < 8; i++) { await press(page, 'ArrowDown'); await pauseForReader(page) }
      await details.focus(); await pauseForReader(page)
    }
    const chart = page.getByRole('region', { name: t('charts.monthlyExpenses') })
    await writeFile(join(output, `${theme}-${language}-accessibility.yml`), await chart.ariaSnapshot())
    // Contrast of visible chart text against its actual inherited/selected background.
    const contrast = await chart.evaluate(section => {
      const luminance = color => { const c = color.slice(0, 3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }); return c[0] * .2126 + c[1] * .7152 + c[2] * .0722 }
      const rgb = css => css.match(/[\d.]+/g).map(Number)
      const background = el => { for (let node = el; node; node = node.parentElement) { const c = rgb(getComputedStyle(node).backgroundColor); if (c.length === 3 || c[3] === 1) return c } return [255,255,255] }
      const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05)
      const walker = document.createTreeWalker(section.parentElement.parentElement, NodeFilter.SHOW_TEXT)
      const values = []; while (walker.nextNode()) { const node = walker.currentNode, el = node.parentElement; if (!node.textContent.trim() || !el.getClientRects().length || el.closest('svg')) continue
        values.push({ text: node.textContent.trim(), ratio: ratio(rgb(getComputedStyle(el).color), background(el)) }) }
      return values
    })
    assert.ok(contrast.length > 30); assert.ok(contrast.every(item => item.ratio >= 4.5), JSON.stringify(contrast.filter(item => item.ratio < 4.5)))
    const outlineRatio = await details.evaluate(el => { const s = getComputedStyle(el); return { color: s.outlineColor, background: getComputedStyle(el.closest('section').parentElement).backgroundColor } })
    const lum = css => { const c = css.match(/[\d.]+/g).slice(0, 3).map(v => { v = Number(v) / 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4 }); return c[0] * .2126 + c[1] * .7152 + c[2] * .0722 }
    const a = lum(outlineRatio.color), b = lum(outlineRatio.background)
    const focusContrast = (Math.max(a, b) + .05) / (Math.min(a, b) + .05)
    assert.ok(focusContrast >= 3)
    contrastResults.push({ theme, language, minimumTextContrast: Math.min(...contrast.map(x => x.ratio)), focusContrast })
    await page.screenshot({ path: join(output, `${theme}-${language}-desktop.png`), fullPage: true })
    // Close, remove-photo and expenses-back names are explicit in both loading/loaded views.
    await page.goto(origin + '/vehicles/1'); await page.getByText('Edit fixture vehicle').click()
    await page.getByRole('button', { name: t('common.close'), exact: true }).waitFor()
    const remove = page.getByRole('button', { name: t('vehicles.removePhoto'), exact: true }); await remove.waitFor()
    await remove.focus(); await pauseForReader(page); await press(page, 'Space'); await pauseForReader(page)
    assert.equal(await remove.count(), 0)
    await page.getByRole('button', { name: t('common.close'), exact: true }).focus(); await pauseForReader(page)
    await press(page, 'Enter'); await page.getByText('Edit fixture vehicle').waitFor()
    results.push(`${theme}/${language}: all 12 months by Tab, Enter/Space, clear and toggle, focus retained, correct filter results, table, labels and contrast`)
    await context.close()
  }
  if (!before && !screenReader) for (const theme of themes) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    await context.addInitScript(theme => { document.addEventListener('DOMContentLoaded', () => document.documentElement.classList.toggle('light', theme === 'light')); localStorage.setItem('language', 'en') }, theme)
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message))
    await page.goto(origin + '/vehicles/1/expenses?year=2026')
    const january = page.getByRole('button', { name: 'January 2026: 1,234.50 GBP', exact: true }); await january.waitFor()
    const months = page.getByRole('group', { name: 'Monthly Expenses' }).getByRole('button')
    for (let i = 0; i < 12; i++) { const box = await months.nth(i).boundingBox(); assert.ok(box.width >= 44 && box.height >= 44) }
    await january.tap(); await page.waitForFunction(() => new URL(location.href).searchParams.get('month') === '1')
    const scroller = page.getByRole('group', { name: 'Monthly Expenses' }).locator('..')
    await scroller.scrollIntoViewIfNeeded()
    const bounds = await scroller.boundingBox()
    const touch = await context.newCDPSession(page)
    const startX = bounds.x + bounds.width - 25, y = bounds.y + bounds.height / 2
    await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: startX, y }] })
    for (let step = 1; step <= 10; step++) {
      await touch.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: startX - step * 20, y }] })
      await page.waitForTimeout(20)
    }
    await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await page.waitForTimeout(200)
    assert.ok(await scroller.evaluate(el => el.scrollLeft > 0), 'Horizontal touch swipe reaches later months')
    assert.equal(new URL(page.url()).searchParams.get('month'), '1', 'Swiping must not activate another filter')
    await page.getByRole('button', { name: 'December 2026: 0.00 GBP' }).tap()
    await page.waitForFunction(() => new URL(location.href).searchParams.get('month') === '12')
    await page.getByRole('button', { name: 'Full Year', exact: true }).tap()
    await page.locator('summary', { hasText: 'Monthly totals' }).tap()
    await page.getByRole('table', { name: 'Monthly totals for 2026' }).waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
    await months.first().evaluate(el => { el.parentElement.parentElement.scrollLeft = 0; window.scrollTo({ top: 0, behavior: 'instant' }) })
    await page.waitForFunction(() => window.scrollY === 0)
    await page.screenshot({ path: join(output, `${theme}-touch.png`), fullPage: true })
    results.push(`${theme}/touch: 44px month targets, swipe/tap/clear including December, readable table, no page overflow`)
    await context.close()
  }
  assert.deepEqual(errors, [])
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, contrastResults, errors, requests }, null, 2))
  console.log(results.join('\n'))
} catch (error) {
  for (const context of browser.contexts()) for (const page of context.pages()) await page.screenshot({ path: join(output, 'failure.png'), fullPage: true }).catch(() => {})
  console.error({ errors }); throw error
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)) }
