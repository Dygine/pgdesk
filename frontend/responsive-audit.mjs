/**
 * Responsive audit over a real browser.
 *
 * Boots the API and serves the built SPA, then for every route in every portal
 * and every viewport width, measures whether the document scrolls horizontally
 * and — crucially — walks the DOM to name the element that causes it.
 *
 * "scrollWidth > innerWidth" alone is a useless finding. The offending element
 * is the finding.
 *
 *   node responsive-audit.mjs [--json out.json]
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const DIST = path.resolve('dist')
const BACKEND = path.resolve('../backend')
const API_PORT = 8021
const WEB_PORT = 4177
const WEB = `http://127.0.0.1:${WEB_PORT}`

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.json': 'application/json', '.woff2': 'font/woff2',
  '.ico': 'image/x-icon', '.png': 'image/png',
}

const VIEWPORTS = [
  { name: '360', width: 360, height: 800 },
  { name: '375', width: 375, height: 812 },
  { name: '390', width: 390, height: 844 },
  { name: '412', width: 412, height: 915 },
  { name: '768', width: 768, height: 1024 },
  { name: '1024', width: 1024, height: 768 },
  { name: '1280', width: 1280, height: 800 },
  { name: '1440', width: 1440, height: 900 },
]

const PUBLIC_ROUTES = ['/login']

const PORTALS = [
  {
    name: 'master',
    email: 'master@pgdesk.local', password: 'Master@2024',
    routes: [
      '/master', '/master/organizations', '/master/organizations/new',
      '/master/subscriptions', '/master/usage', '/master/audit', '/master/settings',
    ],
  },
  {
    name: 'org',
    email: 'owner@sunrise.local', password: 'Owner@2024',
    routes: [
      '/app', '/app/branches', '/app/blueprint', '/app/property', '/app/rooms',
      '/app/beds', '/app/residents', '/app/check-in', '/app/transfer',
      '/app/checkout', '/app/invoices', '/app/payments', '/app/expenses',
      '/app/complaints', '/app/attendance', '/app/scan', '/app/food',
      '/app/laundry', '/app/visitors', '/app/gate-passes', '/app/announcements',
      '/app/queries', '/app/staff', '/app/users', '/app/roles', '/app/inventory',
      '/app/assets', '/app/reports', '/app/audit', '/app/settings',
    ],
  },
  {
    name: 'customer',
    email: 'customer@sunrise.local', password: 'Customer@2024',
    routes: [
      '/me', '/me/rent', '/me/food', '/me/attendance', '/me/scan', '/me/laundry',
      '/me/complaints', '/me/visitors', '/me/gate-pass', '/me/queries',
      '/me/announcements', '/me/profile',
    ],
  },
]

/* ----------------------------------------------------------------- servers */
const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0]
  let file = path.join(DIST, url)
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, 'index.html')
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'text/html' })
  fs.createReadStream(file).pipe(res)
})

const api = spawn('./.venv/bin/python', [
  '-m', 'uvicorn', 'app.main:app',
  '--host', '127.0.0.1', '--port', String(API_PORT), '--log-level', 'warning',
], { cwd: BACKEND, env: { ...process.env } })

api.stderr.on('data', (d) => {
  const t = d.toString()
  if (t.includes('Traceback')) process.stderr.write(t)
})

function shutdown(code) {
  try { api.kill() } catch {}
  try { server.close() } catch {}
  process.exit(code)
}

async function waitForApi(n = 60) {
  for (let i = 0; i < n; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${API_PORT}/health`)
      if (r.ok) return true
    } catch {}
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

/* ------------------------------------------------- the actual measurement */
/**
 * Runs inside the page. Finds every element whose right edge lies beyond the
 * viewport, then keeps only the outermost ones — reporting a leaf <td> when the
 * real culprit is its <table> wastes everyone's time.
 */
const PROBE = `(() => {
  const vw = document.documentElement.clientWidth
  const docScroll = document.documentElement.scrollWidth
  const overflow = docScroll - vw

  const offenders = []
  const all = document.querySelectorAll('body *')
  for (const el of all) {
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) continue
    const style = getComputedStyle(el)
    if (style.visibility === 'hidden' || style.display === 'none') continue
    // Right edge past the viewport, allowing 1px for rounding.
    if (r.right > vw + 1) {
      offenders.push({
        el,
        tag: el.tagName.toLowerCase(),
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 160),
        right: Math.round(r.right),
        width: Math.round(r.width),
        overhang: Math.round(r.right - vw),
      })
    }
  }

  // Drop any offender that has an offending ancestor: report the outermost.
  const outermost = offenders.filter((o) =>
    !offenders.some((p) => p.el !== o.el && p.el.contains(o.el)))

  // A parent that clips its children is not an overflow bug.
  const escaping = outermost.filter((o) => {
    let p = o.el.parentElement
    while (p && p !== document.body) {
      const ov = getComputedStyle(p)
      if (ov.overflowX === 'auto' || ov.overflowX === 'scroll' || ov.overflowX === 'hidden') return false
      p = p.parentElement
    }
    return true
  })

  return {
    vw, docScroll, overflow,
    offenders: escaping.slice(0, 6).map(({ el, ...rest }) => rest),
    contained: outermost.length - escaping.length,
  }
})()`

/* --------------------------------------------------------------------- run */
const results = []
let checks = 0, failures = 0

async function login(page, portal) {
  await page.goto(`${WEB}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 15000 })
  await page.fill('input[type="email"], input[name="email"]', portal.email)
  await page.fill('input[type="password"], input[name="password"]', portal.password)
  await page.click('button[type="submit"]')
  await page.waitForFunction(() => !location.pathname.startsWith('/login'), null, { timeout: 20000 })
}

;(async () => {
  await new Promise((r) => server.listen(WEB_PORT, '127.0.0.1', r))
  process.stdout.write('Starting API… ')
  if (!await waitForApi()) { console.error('API did not start'); shutdown(1) }
  console.log('up')

  const browser = await chromium.launch()

  for (const portal of PORTALS) {
    console.log(`\n=== ${portal.name.toUpperCase()} portal ===`)

    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const consoleErrors = []
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 140)) })

    if (portal.name === 'master') {
      for (const route of PUBLIC_ROUTES) {
        await page.goto(`${WEB}${route}`, { waitUntil: 'domcontentloaded' }).catch(() => {})
        await page.waitForTimeout(600)
        for (const vp of VIEWPORTS) {
          await page.setViewportSize({ width: vp.width, height: vp.height })
          await page.waitForTimeout(90)
          let probe; try { probe = await page.evaluate(PROBE) } catch { continue }
          checks++
          if (probe.overflow > 1) {
            failures++
            results.push({ portal: 'public', viewport: vp.width, route, ...probe })
            const top = probe.offenders[0]
            console.log(`  ${String(vp.name).padStart(4)}px ${route.padEnd(26)} +${String(probe.overflow).padStart(4)}px  ` +
              (top ? `<${top.tag}> ${top.cls.slice(0, 64)}` : '(no escaping element)'))
          }
        }
      }
      await page.setViewportSize({ width: 1440, height: 900 })
    }

    try { await login(page, portal) }
    catch (e) { console.log(`  LOGIN FAILED — ${String(e).split('\n')[0].slice(0, 100)}`); await ctx.close(); continue }

    const perVp = Object.fromEntries(VIEWPORTS.map((v) => [v.name, 0]))

    for (const route of portal.routes) {
      await page.goto(`${WEB}${route}`, { waitUntil: 'domcontentloaded' }).catch(() => {})
      await page.waitForTimeout(700)   // let the route's API calls paint

      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height })
        await page.waitForTimeout(90)
        let probe
        try { probe = await page.evaluate(PROBE) } catch { continue }
        checks++
        if (probe.overflow > 1) {
          failures++
          perVp[vp.name]++
          results.push({ portal: portal.name, viewport: vp.width, route, ...probe })
          const top = probe.offenders[0]
          console.log(`  ${String(vp.name).padStart(4)}px ${route.padEnd(26)} +${String(probe.overflow).padStart(4)}px  ` +
            (top ? `<${top.tag}> ${top.cls.slice(0, 64)}` : '(no escaping element)'))
        }
      }
    }

    const summary = VIEWPORTS.map((v) => `${v.name}:${perVp[v.name]}`).join('  ')
    console.log(`  -- overflowing routes by width -> ${summary}   (of ${portal.routes.length})`)
    if (consoleErrors.length) {
      [...new Set(consoleErrors)].slice(0, 3).forEach((e) => console.log(`  console: ${e}`))
    }
    await ctx.close()
  }

  await browser.close()

  console.log(`\n${'='.repeat(60)}`)
  console.log(`route x viewport checks : ${checks}`)
  console.log(`overflowing             : ${failures}`)

  const jsonIdx = process.argv.indexOf('--json')
  if (jsonIdx > -1 && process.argv[jsonIdx + 1]) {
    fs.writeFileSync(process.argv[jsonIdx + 1], JSON.stringify(results, null, 2))
    console.log(`detail written to       : ${process.argv[jsonIdx + 1]}`)
  }

  shutdown(failures > 0 ? 1 : 0)
})().catch((e) => { console.error(e); shutdown(1) })
