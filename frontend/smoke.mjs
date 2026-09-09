import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import puppeteer from 'puppeteer'

const DIST = path.resolve('dist')
const MIME = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.svg':'image/svg+xml', '.json':'application/json', '.ico':'image/x-icon', '.woff2':'font/woff2' }

/* SPA fallback server — any unknown path serves index.html, like a real host */
const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0]
  let file = path.join(DIST, url)
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'text/html' })
  fs.createReadStream(file).pipe(res)
})
await new Promise((r) => server.listen(4173, '127.0.0.1', r))
const BASE = 'http://127.0.0.1:4173'

/* Authentication is real as of Milestone 2, so the API has to be up for any of
   this to work. CORS is pointed at the test host rather than the dev server. */
const api = spawn('./.venv/bin/python', ['-m', 'uvicorn', 'app.main:app',
                  '--host', '127.0.0.1', '--port', '8000', '--log-level', 'warning'],
                  { cwd: path.resolve('../backend'),
                    env: { ...process.env, CORS_ORIGINS: 'http://127.0.0.1:4173' } })
let apiUp = false
for (let i = 0; i < 60; i++) {
  try { if ((await fetch('http://127.0.0.1:8000/health')).ok) { apiUp = true; break } } catch {}
  await new Promise((r) => setTimeout(r, 400))
}
if (!apiUp) { console.error('backend did not start'); api.kill(); process.exit(1) }

const ROUTES = {
  master: ['/master','/master/organizations','/master/organizations/new','/master/subscriptions','/master/usage','/master/audit','/master/settings'],
  org: ['/app','/app/branches','/app/blueprint','/app/property','/app/rooms','/app/beds','/app/residents',
        '/app/check-in','/app/transfer','/app/checkout','/app/invoices','/app/payments','/app/expenses',
        '/app/complaints','/app/attendance','/app/scan','/app/food','/app/laundry','/app/visitors',
        '/app/gate-passes','/app/announcements','/app/queries','/app/staff','/app/users','/app/roles',
        '/app/inventory','/app/assets','/app/reports','/app/audit','/app/settings'],
  customer: ['/me','/me/rent','/me/food','/me/attendance','/me/scan','/me/laundry','/me/complaints',
             '/me/visitors','/me/gate-pass','/me/queries','/me/announcements','/me/profile'],
}
const CREDS = {
  master:   ['master@pgdesk.local',   'Master@2024'],
  org:      ['owner@sunrise.local',   'Owner@2024'],
  customer: ['customer@sunrise.local','Customer@2024'],
}

/* Every seeded role gets a pass: the sidebar must filter, and a direct URL to a
   forbidden page must render 403 rather than the page. */
const ROLES = [
  ['PG Owner',        'owner@sunrise.local',          'Owner@2024'],
  ['Branch Manager',  'manager@sunrise.local',        'Manager@2024'],
  ['Accountant',      'accounts@sunriselivingpg.com', 'demo1234'],
  ['Receptionist',    'reception@sunriselivingpg.com','demo1234'],
  ['Security',        'security@sunriselivingpg.com', 'demo1234'],
]

const browser = await puppeteer.launch({ args: ['--no-sandbox','--disable-dev-shm-usage'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 900 })
const errors = []
const noise = []
page.on('pageerror', (e) => errors.push(`[PAGEERROR] ${page.url().replace(BASE,'')} :: ${e.message}`))
/* Third-party resource failures (a blocked webfont CDN, for instance) say
   nothing about whether PGDesk works. They are still recorded and printed, but
   a route is only judged failing on a real JS exception or an error raised by
   our own code. Without this every route reports ERR on any network where
   fonts.googleapis.com is unreachable. */
const THIRD_PARTY = /ERR_CERT_|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION_|fonts\.(googleapis|gstatic)\.com/
page.on('console', (m) => {
  if (m.type() !== 'error') return
  const text = m.text().slice(0, 180)
  const entry = `[CONSOLE] ${page.url().replace(BASE, '')} :: ${text}`
  if (THIRD_PARTY.test(text)) { noise.push(entry); return }
  errors.push(entry)
})

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/* One session for the whole run. Creating one per sign-in leaked eight of them
   and the frame detached partway through the RBAC sweep. */
const cdp = await page.createCDPSession()

async function signIn(email, password) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' })
  /* The session lives in an HttpOnly cookie, so localStorage.clear() no longer
     signs anyone out - this harness predates that change. Without clearing the
     cookie the second portal stays logged in as the first and /login redirects
     away before the form ever renders. */
  await cdp.send('Network.clearBrowserCookies')
  await page.goto(BASE + '/login', { waitUntil: 'networkidle0' })
  /* The shell renders "Restoring your session..." until /auth/me answers, so a
     fixed delay races the form. Wait for the field itself. */
  await page.waitForSelector('input[type=email]', { timeout: 20000 })
  await page.evaluate((em, pw) => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    const e = document.querySelector('input[type=email]')
    set.call(e, em); e.dispatchEvent(new Event('input', { bubbles: true }))
    const p = document.querySelector('input[type=password]')
    set.call(p, pw); p.dispatchEvent(new Event('input', { bubbles: true }))
  }, email, password)
  await wait(200)
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => /sign in/i.test(x.textContent))
    if (b) b.click()
  })
  await wait(1600)
  return page.url().replace(BASE, '')
}

let failures = 0
for (const [portal, routes] of Object.entries(ROUTES)) {
  const landed = await signIn(...CREDS[portal])
  console.log(`\n===== ${portal.toUpperCase()} — landed at ${landed} =====`)
  for (const r of routes) {
    const before = errors.length
    await page.goto(BASE + r, { waitUntil: 'networkidle0' })
    await wait(350)
    const info = await page.evaluate(() => ({
      txt: document.body.innerText.replace(/\n+/g, ' | ').trim(),
      url: location.pathname,
    }))
    const bad = errors.length > before
    const blank = info.txt.length < 20
    if (bad || blank) failures++
    console.log(`  ${bad ? 'ERR  ' : blank ? 'BLANK' : 'ok   '} ${r.padEnd(28)} → ${info.url.padEnd(28)} ${info.txt.slice(0, 55)}`)
  }
}

/* ---------------- RBAC pass: nav shape + 403 enforcement per role ---------------- */
console.log('\n\n########## RBAC ##########')
for (const [label, email, password] of ROLES) {
  await signIn(email, password)
  await page.goto(BASE + '/app', { waitUntil: 'networkidle0' })
  await wait(500)
  const nav = await page.evaluate(() =>
    [...document.querySelectorAll('aside a[href^="/app"]')].map((a) => a.getAttribute('href')))
  const visible = [...new Set(nav)]

  let denied = 0, wrongly = 0, crashed = 0
  for (const r of ROUTES.org) {
    const before = errors.length
    await page.goto(BASE + r, { waitUntil: 'networkidle0' })
    await wait(160)
    const state = await page.evaluate(() => {
      const t = document.body.innerText
      if (/Unexpected Application Error/i.test(t)) return 'crash'
      if (/You don.t have access to this page/i.test(t)) return '403'
      return 'ok'
    })
    if (state === 'crash') { crashed++; console.log(`    CRASH ${r}`) }
    else if (state === '403') { denied++; if (visible.includes(r)) { wrongly++; console.log(`    LEAK  ${r} is in the sidebar but 403s`) } }
    else if (!visible.includes(r) && r !== '/app') wrongly++
  }
  console.log(`  ${label.padEnd(16)} nav:${String(visible.length).padStart(2)} reachable  ${String(ROUTES.org.length - denied).padStart(2)}/${ROUTES.org.length} routes  403:${String(denied).padStart(2)}  crashes:${crashed}  nav-mismatch:${wrongly}`)
  if (crashed) failures += crashed
}

console.log(`\n===== ${failures} problem routes, ${errors.length} console/page errors =====`)
;[...new Set(errors)].slice(0, 25).forEach((e) => console.log(e))
if (noise.length) {
  console.log(`\n(${new Set(noise).size} distinct third-party resource failure(s), not counted:`)
  ;[...new Set(noise)].slice(0, 5).forEach((e) => console.log('  ' + e))
  console.log(')')
}
await browser.close()
server.close()
api.kill()
