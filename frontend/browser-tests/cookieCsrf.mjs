/* eslint-disable no-undef */
// Real browser cookies and Fetch Metadata across sibling and cross-site hosts.
// See docs/COOKIE_CSRF.md for the disposable backend and invocation.
import assert from 'node:assert/strict'
import http from 'node:http'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { join, resolve, extname } from 'node:path'
import { createRequire } from 'node:module'

const root = resolve(process.env.GC_FRONTEND || '.')
const output = resolve(process.env.GC_BROWSER_OUTPUT || '/tmp/gearcargo-gc012/browser')
const origin = 'http://cars.gearcargo.test:51912'
const sibling = 'http://evil.gearcargo.test:51912'
const foreign = 'http://attacker.test:51912'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const require = createRequire(join(root, 'package.json'))
await mkdir(output, { recursive: true })
await require('esbuild').build({ entryPoints: [join(root, 'browser-tests/queueHarness.jsx')], bundle: true,
  outfile: join(output, 'harness.js'), format: 'esm', jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'import.meta.env.DEV': 'false' } })

const observed = [], results = []
let blockNetwork = false, omitSource = false, staleProof = false
const server = http.createServer(async (req, res) => {
  try {
    if (req.url === '/attack') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>Attacker</title>'); return }
    if (req.url === '/api/auth/csrf-test') {
      res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><div id="root"></div><script type="module" src="/__harness.js"></script>'); return
    }
    if (req.url === '/__harness.js') { res.setHeader('Content-Type', 'application/javascript'); res.end(await readFile(join(output, 'harness.js'))); return }
    if (req.url.startsWith('/api/') || req.url.startsWith('/__gc007/')) {
      if (blockNetwork) { req.socket.destroy(); return }
      const headers = { ...req.headers, 'x-gc007-fixture': 'disposable-browser-only' }
      if (omitSource && req.method === 'POST') { delete headers.origin; delete headers.referer }
      if (staleProof && req.method === 'POST' && req.url === '/api/vehicles') { headers['x-csrf-token'] = 'expired-test-proof'; staleProof = false }
      const seen = { method: req.method, path: req.url, origin: headers.origin || null,
        site: headers['sec-fetch-site'] || null, cookie: !!headers.cookie?.includes('access_token='), proof: !!headers['x-csrf-token'] }
      observed.push(seen)
      const proxy = http.request({ socketPath: process.env.GC_BACKEND_SOCKET, method: req.method, path: req.url, headers }, response => {
        seen.status = response.statusCode
        res.writeHead(response.statusCode, response.headers); response.pipe(res)
      })
      proxy.on('error', () => { res.statusCode = 502; res.end('Fixture unavailable') }); req.pipe(proxy); return
    }
    const path = req.url.split('?')[0], file = join(root, 'dist', path === '/' ? 'index.html' : path)
    res.setHeader('Content-Type', { '.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json' }[extname(file)] || 'application/octet-stream')
    res.setHeader('Cache-Control', 'no-store'); res.end(await readFile(file))
  } catch { res.statusCode = 404; res.end('Not found') }
})
await new Promise(resolve => server.listen(51912, '127.0.0.1', resolve))
const browser = await chromium.launch({ headless: true, executablePath: process.env.GC_CHROMIUM,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--no-proxy-server',
    '--host-resolver-rules=MAP *.gearcargo.test 127.0.0.1, MAP attacker.test 127.0.0.1',
    `--unsafely-treat-insecure-origin-as-secure=${origin}`] })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn, label) { for (let i = 0; i < 450; i++) { if (await fn()) return; await pause(100) } throw new Error(`Timed out: ${label}`) }
async function message(page, type) {
  return page.evaluate(type => new Promise((resolve, reject) => {
    const channel = new MessageChannel(), timeout = setTimeout(() => reject(new Error('Worker timeout')), 15000)
    channel.port1.onmessage = event => { clearTimeout(timeout); resolve(event.data) }
    navigator.serviceWorker.controller.postMessage({ type }, [channel.port2])
  }), type)
}
try {
  const context = await browser.newContext(), page = await context.newPage()
  await page.goto(`${origin}/api/auth/csrf-test`)
  await page.waitForFunction(() => window.gc007 && !window.gc007.auth.isLoading)
  await page.evaluate(async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready })
  await page.waitForFunction(() => !!navigator.serviceWorker.controller)
  assert.equal(await page.evaluate(async () => (await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'queue-a@example.invalid', password: 'BrowserFixture123!' }) })).status), 403)
  await page.evaluate(() => gc007.auth.login('queue-a@example.invalid', 'BrowserFixture123!'))
  await page.waitForFunction(() => gc007.auth.user?.username === 'queue_A')
  const vehicle = await page.evaluate(async () => (await gc007.api.post('/vehicles', { name: 'Protected vehicle' })).data.vehicle)
  assert(vehicle.id)
  results.push({ scenario: 'Worker-controlled anonymous bootstrap, protected login and trusted cookie mutation', passed: true })

  const attack = await context.newPage()
  await attack.goto(`${sibling}/attack`)
  const path = `/api/vehicles/${vehicle.id}/archive`
  await attack.evaluate(async url => { await fetch(url, { method: 'POST', mode: 'no-cors', credentials: 'include' }) }, origin + path)
  const siblingRequest = observed.findLast(row => row.path === path && row.origin === sibling)
  assert.equal(siblingRequest?.cookie, true, 'Strict cookies really were sent from the same-site sibling')
  assert.equal(siblingRequest.site, 'same-site'); assert.equal(siblingRequest.status, 403)
  results.push({ scenario: 'Malicious same-site sibling sends real Strict auth cookies but bodyless archive is rejected', passed: true })

  await attack.evaluate(url => { const form = document.createElement('form'); form.method = 'POST'; form.action = url; form.target = 'sink'; const frame = document.createElement('iframe'); frame.name = 'sink'; document.body.append(frame, form); form.submit() }, origin + path)
  await until(() => observed.filter(row => row.path === path && row.origin === sibling && row.status === 403).length === 2, 'simple form rejection')
  await attack.evaluate(async url => { try { await fetch(url, { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': 'forged' } }) } catch { /* CORS blocks preflight */ } }, origin + path)
  assert(observed.some(row => row.method === 'OPTIONS' && row.path === path && row.origin === sibling))
  assert.equal(observed.filter(row => row.method === 'POST' && row.path === path && row.origin === sibling).length, 2)
  results.push({ scenario: 'Simple form rejected; malicious custom-header preflight cannot authorize a mutation', passed: true })

  await attack.goto(`${foreign}/attack`)
  await attack.evaluate(async url => { await fetch(url, { method: 'POST', mode: 'no-cors', credentials: 'include' }) }, origin + path)
  const crossSite = observed.findLast(row => row.path === path && row.origin === foreign)
  assert.equal(crossSite?.site, 'cross-site'); assert.equal(crossSite.status, 403)
  assert.equal(crossSite.cookie, false, 'SameSite also prevents cross-site auth cookies')
  const unchanged = await page.evaluate(async id => (await gc007.api.get(`/vehicles/${id}`)).data, vehicle.id)
  assert.equal(unchanged.archived, false)
  results.push({ scenario: 'Cross-site request rejected and all attack attempts leave the vehicle unchanged', passed: true })

  omitSource = true
  assert.equal(await page.evaluate(async () => (await gc007.api.post('/vehicles', { name: 'Headerless with proof' })).status), 201)
  assert.equal(await page.evaluate(async () => (await fetch('/api/vehicles', { method: 'POST' })).status), 403)
  omitSource = false
  results.push({ scenario: 'Proxy-stripped Origin/Referer still requires valid session proof', passed: true })

  staleProof = true
  assert.equal(await page.evaluate(async () => (await gc007.api.post('/vehicles', { name: 'Stale proof retry' })).status), 201)
  const beforeRefresh = await page.evaluate(async () => (await (await fetch('/api/csrf-token')).json()).csrf_token)
  assert.equal(await page.evaluate(async () => (await gc007.api.post('/auth/refresh')).status), 200)
  assert.equal(await page.evaluate(async token => (await fetch('/api/vehicles', { method: 'POST', headers: { 'X-CSRF-Token': token, 'Content-Type': 'application/json' }, body: '{"name":"stale"}' })).status, beforeRefresh), 403)
  results.push({ scenario: 'Stale-proof retry succeeds once; authentication refresh rotates browser proof', passed: true })

  blockNetwork = true
  assert.equal(await page.evaluate(async () => { try { await gc007.api.post('/vehicles', { name: 'Offline CSRF replay' }); return 'saved' } catch (error) { return error.code } }), 'OFFLINE_QUEUED')
  blockNetwork = false
  await until(async () => { await message(page, 'FORCE_SYNC'); return (await page.evaluate(async () => (await (await fetch('/__gc007/records')).json()).A)).includes('Offline CSRF replay') }, 'offline replay with fresh proof')
  const names = await page.evaluate(async () => (await (await fetch('/__gc007/records')).json()).A)
  assert.equal(names.filter(name => name === 'Offline CSRF replay').length, 1)
  const cachedProof = await page.evaluate(async () => { for (const name of await caches.keys()) if ((await (await caches.open(name)).keys()).some(request => ['/api/csrf-token', '/api/auth/csrf-token'].includes(new URL(request.url).pathname))) return true; return false })
  assert.equal(cachedProof, false)
  results.push({ scenario: 'Offline draft survives token endpoint outage and replays exactly once; proof is never cached', passed: true })

  assert.equal(await page.evaluate(async () => (await fetch('/api/auth/logout', { method: 'POST' })).status), 403)
  await page.evaluate(() => gc007.auth.logout())
  assert.equal(await page.evaluate(async () => (await fetch('/api/auth/me')).status), 401)
  results.push({ scenario: 'Logout requires proof and succeeds through the real authentication client', passed: true })
  console.log(JSON.stringify({ results, observed }, null, 2))
  await writeFile(join(output, 'results.json'), JSON.stringify({ results, observed }, null, 2))
  await context.close()
} finally { await writeFile(join(output, 'observed.json'), JSON.stringify({ results, observed }, null, 2)); await browser.close(); await new Promise(resolve => server.close(resolve)) }
