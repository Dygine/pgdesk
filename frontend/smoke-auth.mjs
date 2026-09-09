/**
 * Milestone 2 end-to-end check.
 *
 * Boots the real FastAPI process, serves the built SPA, then drives a headless
 * browser through login for every seeded role. Nothing here is stubbed.
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import puppeteer from 'puppeteer'

const DIST = path.resolve('dist')
const MIME = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css',
               '.svg':'image/svg+xml', '.json':'application/json', '.woff2':'font/woff2' }

/* ---- backend ---- */
const api = spawn('./.venv/bin/python', ['-m', 'uvicorn', 'app.main:app',
                  '--host', '127.0.0.1', '--port', '8000', '--log-level', 'warning'],
                  { cwd: path.resolve('../backend'),
                    env: { ...process.env,
                           // The test host is 4173, not the dev server's 5173.
                           CORS_ORIGINS: 'http://127.0.0.1:4173,http://localhost:4173' } })
api.stderr.on('data', (d) => { const s = String(d); if (/Traceback|CRITICAL/.test(s)) console.error('API:', s) })

const waitForApi = async () => {
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch('http://127.0.0.1:8000/health'); if (r.ok) return true } catch {}
    await new Promise(r => setTimeout(r, 400))
  }
  return false
}
if (!await waitForApi()) { console.error('backend never came up'); api.kill(); process.exit(1) }
console.log('backend up\n')

/* ---- SPA host ---- */
const spa = http.createServer((req, res) => {
  const url = req.url.split('?')[0]
  let file = path.join(DIST, url)
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'text/html' })
  fs.createReadStream(file).pipe(res)
})
await new Promise(r => spa.listen(4173, '127.0.0.1', r))
const BASE = 'http://127.0.0.1:4173'

const browser = await puppeteer.launch({ args: ['--no-sandbox','--disable-dev-shm-usage'] })
const wait = (ms) => new Promise(r => setTimeout(r, ms))
let failures = 0

async function signIn(page, email, password, { fresh = false } = {}) {
  // localStorage is shared across pages in one browser context, so an earlier
  // role would still be signed in and /login would redirect away.
  if (fresh) {
    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
    await page.evaluate(() => localStorage.clear())
  }
  await page.goto(BASE + '/login', { waitUntil: 'networkidle0' })
  /* The shell renders "Restoring your session..." until /auth/me answers, so a
     fixed delay races the form. Wait for the field itself. */
  await page.waitForSelector('input[type=email]', { timeout: 20000 })
  const ready = await page.evaluate(() => !!document.querySelector('input[type=email]'))
  if (!ready) return 'NO_LOGIN_FORM:' + page.url().replace('http://127.0.0.1:4173', '')
  await page.evaluate((em, pw) => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    const e = document.querySelector('input[type=email]')
    set.call(e, em); e.dispatchEvent(new Event('input', { bubbles: true }))
    const p = document.querySelector('input[type=password]')
    set.call(p, pw); p.dispatchEvent(new Event('input', { bubbles: true }))
  }, email, password)
  await wait(200)
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(x => /sign in/i.test(x.textContent))
    if (b) b.click()
  })
  await wait(1800)
  return page.url().replace(BASE, '')
}

const ROLES = [
  ['Master Admin',   'master@pgdesk.local',            'Master@2024',  '/master'],
  ['PG Owner',       'owner@sunrise.local',            'Owner@2024',   '/app'],
  ['Branch Manager', 'manager@sunrise.local',          'Manager@2024', '/app'],
  ['Accountant',     'accounts@sunriselivingpg.com',   'demo1234',     '/app'],
  ['Security',       'security@sunriselivingpg.com',   'demo1234',     '/app'],
  ['Resident',       'customer@sunrise.local',         'Customer@2024','/me'],
]

console.log('=== ROLE ROUTING ===')
for (const [label, email, password, expected] of ROLES) {
  const page = await browser.newPage()
  const errs = []
  page.on('pageerror', e => errs.push(e.message))
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 120)) })
  page.on('requestfailed', r => errs.push('netfail: ' + r.url().slice(0, 60) + ' ' + (r.failure()?.errorText || '')))
  const landed = await signIn(page, email, password, { fresh: true })
  const info = await page.evaluate(() => ({
    nav: [...new Set([...document.querySelectorAll('aside a[href]')].map(a => a.getAttribute('href')))].length,
    hasToken: !!localStorage.getItem('pgdesk.auth.tokens'),
    text: document.body.innerText.slice(0, 45).replace(/\n/g, ' '),
  }))
  const ok = landed.startsWith(expected) && errs.length === 0
  if (!ok) failures++
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label.padEnd(15)} -> ${landed.padEnd(9)} nav:${String(info.nav).padStart(2)} token:${info.hasToken ? 'y' : 'n'} ${errs[0] || ''}`)
  await page.close()
}

console.log('\n=== SESSION BEHAVIOUR ===')
const page = await browser.newPage()

await signIn(page, 'owner@sunrise.local', 'Owner@2024', { fresh: true })
await page.reload({ waitUntil: 'networkidle0' }); await wait(1500)
let url = page.url().replace(BASE, '')
console.log(`  ${url.startsWith('/app') ? 'ok  ' : 'FAIL'} session survives a page reload -> ${url}`)
if (!url.startsWith('/app')) failures++

const perms = await page.evaluate(async () => {
  const t = JSON.parse(localStorage.getItem('pgdesk.auth.tokens'))
  const r = await fetch('http://127.0.0.1:8000/api/v1/auth/me',
                        { headers: { Authorization: `Bearer ${t.access_token}` } })
  return (await r.json()).data.permissions.length
})
console.log(`  ${perms === 116 ? 'ok  ' : 'FAIL'} permissions come from the backend -> ${perms}`)
if (perms !== 98) failures++

// A dead token must send the user back to login rather than hanging.
await page.evaluate(() => localStorage.setItem('pgdesk.auth.tokens',
  JSON.stringify({ access_token: 'bad.token.here', refresh_token: 'also-bad-'.repeat(3) })))
await page.goto(BASE + '/app', { waitUntil: 'networkidle0' }); await wait(1800)
url = page.url().replace(BASE, '')
console.log(`  ${url.startsWith('/login') ? 'ok  ' : 'FAIL'} invalid token redirects to login -> ${url}`)
if (!url.startsWith('/login')) failures++

await signIn(page, 'owner@sunrise.local', 'Owner@2024', { fresh: true })
await page.evaluate(() => {
  const b = document.querySelector('button[aria-haspopup="menu"]')
  if (b) b.click()
})
await wait(400)
await page.evaluate(() => {
  const b = [...document.querySelectorAll('button,[role=menuitem]')].find(x => /sign out|log ?out/i.test(x.textContent))
  if (b) b.click()
})
await wait(1500)
const afterLogout = await page.evaluate(() => ({
  url: location.pathname, token: localStorage.getItem('pgdesk.auth.tokens'),
}))
const logoutOk = afterLogout.url.startsWith('/login') && !afterLogout.token
console.log(`  ${logoutOk ? 'ok  ' : 'FAIL'} logout clears the session -> ${afterLogout.url} token:${afterLogout.token ? 'still set' : 'cleared'}`)
if (!logoutOk) failures++

const bad = await signIn(page, 'owner@sunrise.local', 'wrong-password', { fresh: true })
const msg = await page.evaluate(() => document.body.innerText.match(/incorrect[^\n]*/i)?.[0] || '')
console.log(`  ${bad.startsWith('/login') ? 'ok  ' : 'FAIL'} wrong password stays on login -> "${msg}"`)
if (!bad.startsWith('/login')) failures++

console.log(`\n===== ${failures} failures =====`)
await browser.close(); spa.close(); api.kill()
process.exit(failures ? 1 : 0)
