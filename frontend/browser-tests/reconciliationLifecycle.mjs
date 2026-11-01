/* eslint-disable no-undef */
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, readdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'
const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-reconciliation-proposal9/browser')
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/reconciliationHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })
const css = (await readdir(join(root, 'dist/assets'))).find(name => name.endsWith('.css'))
const uploaded = []
const errors = []
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/api/auth/reconciliation-test') {
      res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/style.css"><div id="root"></div><script type="module" src="/__reconciliation-harness.js"></script>'); return
    }
    if (req.url === '/__reconciliation-harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url === '/style.css') { res.setHeader('Content-Type', 'text/css'); res.end(await readFile(join(root, 'dist/assets', css))); return }
    if (req.url.startsWith('/api/')) {
      if (req.method === 'POST' && req.url.startsWith('/api/reconciliation')) { const parts = []; req.on('data', part => parts.push(part)); req.on('end', () => uploaded.push(Buffer.concat(parts).toString())) }
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
    await page.goto(origin + '/api/auth/reconciliation-test')
    await page.waitForFunction(() => window.reconciliationFixture && !window.reconciliationFixture.auth.isLoading)
    await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
    await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  }
  const go = async path => page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)
  const csv = 'Date;Amount;Currency;Vendor;Account\r\n01/10/2026;-100,00;GBP;Garage;SECRET-ACCOUNT\r\n02/10/2026;20,00;GBP;Refund;SECRET-ACCOUNT\r\n03/10/2026;-9,99;GBP;PRIVATE-TRANSACTION;SECRET-ACCOUNT'
  await open()
  await page.evaluate(() => window.reconciliationFixture.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => window.reconciliationFixture.auth.isAuthenticated)
  await go('/reconciliation')
  const prepare = async () => {
    await page.getByLabel('Choose local CSV').setInputFiles({name:'statement.csv',mimeType:'text/csv',buffer:Buffer.from(csv)})
    await page.getByLabel('Statement name',{exact:true}).fill('October selected')
    await page.getByLabel('Column separator',{exact:true}).selectOption(';')
    await page.getByLabel('Decimal separator',{exact:true}).selectOption(',')
    await page.getByLabel('Date format',{exact:true}).selectOption('dmy')
    await page.getByLabel('Amount convention',{exact:true}).selectOption('bank')
    await page.getByLabel('Date',{exact:true}).selectOption('0')
    await page.getByLabel('Signed amount',{exact:true}).selectOption('1')
    await page.getByLabel('Original currency',{exact:true}).selectOption('2')
    await page.getByLabel('Vendor (optional)',{exact:true}).selectOption('3')
    await page.getByLabel('Include row 2',{exact:true}).check()
    await page.getByLabel('Include row 3',{exact:true}).check()
    await page.getByRole('button',{name:'Preview locally',exact:true}).click()
    await page.getByRole('heading',{name:'Only this data will be uploaded'}).waitFor()
  }
  await prepare()
  assert.equal(uploaded.length,0,'local parsing and preview must not upload statement content')
  await page.screenshot({path:join(output,'local-preview.png'),fullPage:true})
  await page.getByRole('button',{name:'Upload selected transactions',exact:true}).click()
  await page.getByRole('heading',{name:'October selected · Open'}).waitFor()
  assert.ok(uploaded.length>=2)
  assert.ok(uploaded.every(body=>!body.includes('SECRET-ACCOUNT')&&!body.includes('PRIVATE-TRANSACTION')&&!body.includes('Account')))
  const initial = await page.evaluate(async()=> (await window.reconciliationFixture.api.get('/services?vehicle_id=1')).data)
  const saveRow=async () => {
    const [response]=await Promise.all([page.waitForResponse(r=>/\/api\/reconciliation\/1\/rows\/\d+$/.test(new URL(r.url()).pathname)&&r.request().method()==='PUT'),page.getByRole('button',{name:'Confirm row changes',exact:true}).click()])
    assert.equal(response.status(),200,await response.text())
    await page.getByRole('region',{name:'Review',exact:true}).waitFor({state:'detached'})
  }
  await page.getByRole('button',{name:'Review',exact:true}).nth(0).click()
  await page.getByLabel('Signed amount Invoice A',{exact:true}).fill('40.00')
  await page.getByLabel('Signed amount Invoice B',{exact:true}).fill('60.00')
  await saveRow()
  await page.getByRole('button',{name:'Review',exact:true}).nth(1).click()
  await page.getByLabel('Signed amount Refund',{exact:true}).fill('-20.00')
  await saveRow()
  await page.getByRole('button',{name:'Mark reconciled',exact:true}).click()
  await page.getByRole('heading',{name:'October selected · Reconciled'}).waitFor()
  const ledger=await page.evaluate(async()=> (await window.reconciliationFixture.api.get('/services?vehicle_id=1')).data)
  assert.deepEqual(ledger,initial)
  await page.screenshot({path:join(output,'reconciled.png'),fullPage:true})
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Export summary CSV',exact:true}).click()])
  await download.saveAs(join(output,'summary.csv'))
  assert.match(await readFile(join(output,'summary.csv'),'utf8'),/-20.00/)
  await page.getByRole('button',{name:'Back to statements',exact:true}).click()
  await prepare()
  await page.getByRole('button',{name:'Upload selected transactions',exact:true}).click()
  await page.getByRole('heading',{name:'October selected · Reconciled'}).waitFor()
  assert.equal(await page.evaluate(async()=>(await window.reconciliationFixture.api.get('/reconciliation')).data.batches.length),1)
  // Review a partial row, preserve an unusual original currency in the draft.
  await page.evaluate(async()=>{
    const api=window.reconciliationFixture.api
    await api.post('/reconciliation',{name:'Missing receipt',source_key:'b'.repeat(64),rows:[{row_number:2,date:'2026-10-03',amount:'15.25',currency:'CHF',vendor:'Swiss garage'}]},{headers:{'X-GearCargo-Mutation-Version':'1','Idempotency-Key':crypto.randomUUID()}})
  })
  await go('/reconciliation?batch=2')
  await page.getByRole('button',{name:'Review',exact:true}).click()
  await page.getByLabel('Vehicle',{exact:true}).selectOption('1')
  await page.getByRole('button',{name:'Open expense draft',exact:true}).click()
  await page.waitForURL('**/vehicles/1/service/add')
  await page.locator('[name="total_cost"]').waitFor()
  assert.equal(await page.locator('[name="total_cost"]').inputValue(),'15.25')
  assert.equal(await page.locator('[name="currency"]').inputValue(),'CHF')
  assert.equal(await page.locator('[name="shop_name"]').inputValue(),'Swiss garage')
  assert.ok(!(await page.evaluate(()=>JSON.stringify(history.state))).includes('Swiss garage'))
  // Existing expense form explicitly saves; returning does not auto-match.
  await page.getByRole('button',{name:/Inspection/i}).first().click()
  const [created]=await Promise.all([page.waitForResponse(r=>new URL(r.url()).pathname==='/api/services'&&r.request().method()==='POST'),page.getByRole('button',{name:'Save',exact:true}).click()])
  assert.equal(created.status(),201,await created.text())
  await page.waitForURL('**/reconciliation?batch=2')
  await go('/vehicles/1/service/add?edit=4')
  await page.locator('[name="currency"]').waitFor()
  assert.equal(await page.locator('[name="currency"]').inputValue(),'CHF','editing a saved draft must retain its original currency')
  await go('/reconciliation?batch=2')
  await page.getByText('Unmatched',{exact:true}).waitFor()
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:join(output,'mobile-unmatched.png'),fullPage:true})
  // Final actions cannot enter the offline mutation queue.
  await page.getByRole('button',{name:'Review',exact:true}).click()
  await context.setOffline(true)
  await page.getByRole('button',{name:'Confirm row changes',exact:true}).click()
  await page.getByText('Connect to the internet before confirming statement changes.',{exact:true}).waitFor()
  assert.equal(await page.evaluate(()=>window.reconciliationFixture.mutationDb.pending.count()),0)
  await context.setOffline(false)
  await go('/reconciliation?batch=1')
  await page.getByRole('button',{name:'Delete statement data',exact:true}).click()
  await page.getByRole('dialog').getByRole('button',{name:'Delete statement data',exact:true}).click()
  await page.getByRole('heading',{name:'Saved statements',exact:true}).waitFor()
  assert.equal(await page.evaluate(async()=>(await window.reconciliationFixture.api.get('/services?vehicle_id=1')).data.entries.length),4)
  assert.equal(await page.evaluate(async()=>{
    for(const name of await caches.keys()) for(const request of await (await caches.open(name)).keys()) if(new URL(request.url).pathname.startsWith('/api/reconciliation')) return true
    return false
  }),false,'selected statement data must not persist in service-worker caches')
  assert.deepEqual(errors,[])
  await writeFile(join(output,'result.json'),JSON.stringify({passed:true,checks:['local selection privacy','signed split/refund','unchanged ledger','CSV export','same-file replay','currency-preserving draft/save/return','offline rejection','source deletion preserves expenses'],screenshots:3},null,2))
  console.log('Browser reconciliation workflow passed')
  await context.close()
} catch (error) { for (const context of browser.contexts()) for (const page of context.pages()) { await page.screenshot({path:join(output,'failure.png'),fullPage:true}); await writeFile(join(output,'failure.txt'),await page.locator('body').innerText()) } throw error } finally { await browser.close(); await new Promise(resolve=>server.close(resolve)) }
