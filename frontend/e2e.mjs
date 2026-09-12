/**
 * End-to-end critical path, over real HTTP against a real server.
 *
 * Boots uvicorn against the development database, then walks the whole product
 * the way a client does: master admin creates an organisation, the owner signs
 * in, builds property, admits a resident, bills and collects, runs the gate and
 * the helpdesk, and the resident sees their own data and nothing else.
 *
 * No browser. `smoke.mjs` and `smoke-auth.mjs` drive a headless Chrome and need
 * puppeteer installed; this one needs nothing but node, so it runs in CI and in
 * a container where Chrome does not exist. What it gives up is rendering — what
 * it keeps is every authorisation and business rule, which is the part that
 * matters and the part a browser test tends to assert least.
 *
 *   node e2e.mjs
 */
import { spawn } from 'node:child_process'
import path from 'node:path'
import process from 'node:process'

const API = 'http://127.0.0.1:8009/api/v1'
const BACKEND = path.resolve('../backend')

let passed = 0
let failed = 0
const failures = []

function check(name, condition, detail = '') {
  if (condition) {
    passed++
    console.log(`  \x1b[32mPASS\x1b[0m ${name}`)
  } else {
    failed++
    failures.push(`${name}${detail ? ` — ${detail}` : ''}`)
    console.log(`  \x1b[31mFAIL\x1b[0m ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

function section(title) {
  console.log(`\n\x1b[1m${title}\x1b[0m`)
}

/* Cookies are kept per identity, because the refresh session is a cookie now
   and two signed-in actors must not share one jar. */
function makeClient() {
  const jar = new Map()
  let accessToken = null

  return {
    get token() { return accessToken },
    setToken(t) { accessToken = t },
    async call(method, pathname, body, { auth = true } = {}) {
      const headers = { 'Content-Type': 'application/json', 'X-PGuru-Auth': '1' }
      if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`
      if (jar.size) {
        headers.Cookie = [...jar.entries()].map(([k, v]) => `${k}=${v}`).join('; ')
      }
      const res = await fetch(`${API}${pathname}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      })
      const setCookie = res.headers.getSetCookie?.() || []
      for (const raw of setCookie) {
        const [pair] = raw.split(';')
        const idx = pair.indexOf('=')
        const name = pair.slice(0, idx)
        const value = pair.slice(idx + 1)
        if (value === '' || raw.includes('Max-Age=0')) jar.delete(name)
        else jar.set(name, value)
      }
      let payload = null
      try { payload = await res.json() } catch { /* empty body */ }
      return { status: res.status, body: payload, cookies: jar }
    },
  }
}

async function login(client, email, password) {
  const r = await client.call('POST', '/auth/login', { email, password }, { auth: false })
  if (r.status === 200) client.setToken(r.body.data.access_token)
  return r
}

/* ---------------------------------------------------------------- server */
const api = spawn(process.env.PGGURU_PYTHON || './.venv/bin/python', ['-m', 'uvicorn', 'app.main:app',
  '--host', '127.0.0.1', '--port', '8009', '--log-level', 'warning'],
  { cwd: BACKEND, env: { ...process.env } })

api.stderr.on('data', (d) => {
  const text = d.toString()
  if (text.includes('Traceback') || text.includes('ERROR')) process.stderr.write(text)
})

async function waitForApi(attempts = 60) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch('http://127.0.0.1:8009/health')
      if (res.ok) return true
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500))
  }
  return false
}

function shutdown(code) {
  api.kill('SIGTERM')
  // Synchronous exit: an async shutdown let the script carry on running
  // assertions against a server it had just decided to stop.
  setTimeout(() => { api.kill('SIGKILL') }, 200)
  process.exit(code)
}

/* ------------------------------------------------------------------ run */
const unique = Date.now().toString(36)

try {
  console.log('Starting API…')
  if (!await waitForApi()) {
    console.error('API did not come up on port 8009')
    shutdown(1)
  }

  // ------------------------------------------------------------ 1. master
  section('1. Master admin')
  const master = makeClient()
  const masterLogin = await login(master, 'master@pgguru.local', 'Master@2024')
  check('master signs in', masterLogin.status === 200, `status ${masterLogin.status}`)
  if (masterLogin.status !== 200) {
    console.error('\nCannot continue without the seeded master account. Run: python seed.py')
    shutdown(1)
  }
  check('refresh token is NOT in the login body',
    !JSON.stringify(masterLogin.body).includes('refresh_token'))
  check('refresh session cookie was set', masterLogin.cookies.has('pgguru_refresh'))

  const dashboard = await master.call('GET', '/master/dashboard')
  check('master dashboard loads', dashboard.status === 200)

  // ------------------------------------------------ 2. create organisation
  section('2. Create an organisation')
  const plans = await master.call('GET', '/master/plans')
  check('plans list loads', plans.status === 200)
  const planCode = plans.body?.data?.[0]?.code

  const created = await master.call('POST', '/master/organizations', {
    name: `E2E PG ${unique}`,
    owner_name: 'E2E Owner',
    owner_email: `owner.${unique}@e2e-pgguru.com`,
    plan_code: planCode,
    city: 'Bengaluru',
  })
  check('organisation is created', created.status === 201, `status ${created.status} ${JSON.stringify(created.body?.message || '')}`)
  // The endpoint returns { organization, owner } - not a flat organisation.
  const orgId = created.body?.data?.organization?.id

  /* The API generates the owner's first password and returns it once; it is not
     something the caller chooses. The account is flagged must_change_password,
     so the real first-run journey is: sign in with the temporary password, then
     immediately change it. Exercising that is the point of this section. */
  const tempPassword = created.body?.data?.owner?.temporary_password
  check('a temporary owner password was issued', Boolean(tempPassword))
  check('the new owner must change it on first sign-in',
    created.body?.data?.owner?.must_change_password === true)

  // ------------------------------------------------------- 3. owner signs in
  section('3. PG owner')
  const owner = makeClient()
  const ownerEmail = `owner.${unique}@e2e-pgguru.com`
  const ownerLogin = await login(owner, ownerEmail, tempPassword)
  check('new owner signs in with the temporary password', ownerLogin.status === 200,
    `status ${ownerLogin.status}`)
  if (ownerLogin.status !== 200) shutdown(1)
  check('login reports must_change_password',
    ownerLogin.body?.data?.user?.must_change_password === true)

  const changed = await owner.call('POST', '/auth/change-password', {
    current_password: tempPassword, new_password: 'E2eOwner@2026',
  })
  check('owner changes the temporary password', changed.status === 200, `status ${changed.status}`)

  const reLogin = await login(owner, ownerEmail, 'E2eOwner@2026')
  check('owner signs in with the new password', reLogin.status === 200, `status ${reLogin.status}`)
  check('the temporary password no longer works',
    (await login(makeClient(), ownerEmail, tempPassword)).status === 401)

  const me = await owner.call('GET', '/auth/me')
  check('owner /auth/me resolves their organisation',
    me.body?.data?.organization?.id === orgId)
  check('owner cannot reach master endpoints',
    (await owner.call('GET', '/master/organizations')).status === 403)

  // -------------------------------------------------------- 4. property
  section('4. Property hierarchy')
  const branch = await owner.call('POST', '/branches', {
    name: 'Koramangala', code: `K${unique.slice(-4)}`, city: 'Bengaluru',
  })
  check('branch created', branch.status === 201, JSON.stringify(branch.body?.message || ''))
  const branchId = branch.body?.data?.id

  const building = await owner.call('POST', '/buildings', {
    branch_id: branchId, name: 'Block A', code: `A${unique.slice(-3)}`,
  })
  check('building created', building.status === 201)
  const buildingId = building.body?.data?.id

  const floor = await owner.call('POST', '/floors', {
    branch_id: branchId, building_id: buildingId, floor_number: 1, name: 'Ground',
  })
  check('floor created', floor.status === 201)
  const floorId = floor.body?.data?.id

  const room = await owner.call('POST', '/rooms', {
    branch_id: branchId, building_id: buildingId, floor_id: floorId,
    room_number: '101', room_type: 'Double sharing', rent_amount: 9000,
    // Rooms generate their beds from capacity by default, which would collide
    // with the explicit bed created below. This test wants to exercise manual
    // bed creation, so opt out.
    generate_beds: false,
  })
  check('room created', room.status === 201)
  const roomId = room.body?.data?.id

  const bed = await owner.call('POST', '/beds', {
    branch_id: branchId, room_id: roomId, bed_number: 'A', rent_amount: 9000,
  })
  check('bed created', bed.status === 201)
  const bedId = bed.body?.data?.id

  // -------------------------------------------------------- 5. resident
  section('5. Resident admission')
  const resident = await owner.call('POST', '/residents', {
    first_name: 'Arjun', last_name: 'Rao', phone: `+9198${unique.slice(-8)}`,
    email: `arjun.${unique}@e2e-pgguru.com`, branch_id: branchId,
    // Portal access is opt-in, and the API issues the first password itself -
    // the caller does not choose it, exactly as for a new organisation owner.
    create_portal_login: true,
  })
  check('resident created', resident.status === 201, JSON.stringify(resident.body?.message || ''))
  const residentId = resident.body?.data?.id
  const residentPassword = resident.body?.data?.credentials?.temporary_password
  check('resident portal credentials were issued', Boolean(residentPassword))

  const available = await owner.call('GET', '/residents/available-beds')
  check('the new bed shows as available',
    (available.body?.data || []).some((b) => b.id === bedId))

  const checkIn = await owner.call('POST', `/residents/${residentId}/check-in`, {
    bed_id: bedId, monthly_rent: 9000, security_deposit: 18000,
    meal_plan: 'Two meals', food_charge: 2400, raise_invoice: true,
  })
  check('check-in succeeds', checkIn.status === 200, JSON.stringify(checkIn.body?.message || ''))
  check('check-in raised the first invoice', Boolean(checkIn.body?.data?.invoice?.id))
  const invoiceId = checkIn.body?.data?.invoice?.id
  const invoiceTotal = checkIn.body?.data?.invoice?.total

  const takenBed = await owner.call('GET', '/residents/available-beds')
  check('the bed is no longer offered',
    !(takenBed.body?.data || []).some((b) => b.id === bedId))

  // --------------------------------------------------------- 6. money
  section('6. Billing and payment')
  const payment = await owner.call('POST', '/payments', {
    resident_id: residentId, invoice_id: invoiceId,
    amount: invoiceTotal, method: 'UPI', reference: `E2E-${unique}`,
  })
  check('payment recorded', [200, 201].includes(payment.status),
    JSON.stringify(payment.body?.message || ''))
  const paymentId = payment.body?.data?.id

  const verified = await owner.call('POST', `/payments/${paymentId}/verify`, { approved: true })
  check('payment verified', verified.status === 200)

  const invoice = await owner.call('GET', `/invoices/${invoiceId}`)
  check('invoice is settled', invoice.body?.data?.status === 'PAID',
    `status ${invoice.body?.data?.status}`)

  // ---------------------------------------------------- 7. operations
  section('7. Gate, visitors and helpdesk')
  const attendance = await owner.call('POST', '/attendance', {
    resident_id: residentId, status: 'PRESENT',
  })
  check('attendance marked', [200, 201].includes(attendance.status))

  const visitor = await owner.call('POST', '/visitors', {
    resident_id: residentId, name: 'Ramesh Rao', phone: '+919845000111',
    relation: 'Father',
  })
  check('visitor logged', visitor.status === 201)
  const visitorId = visitor.body?.data?.id

  check('unapproved visitor cannot enter',
    (await owner.call('POST', `/visitors/${visitorId}/entry`)).status === 409)
  check('visitor approved',
    (await owner.call('POST', `/visitors/${visitorId}/decision`, { approved: true })).status === 200)
  check('approved visitor enters',
    (await owner.call('POST', `/visitors/${visitorId}/entry`)).status === 200)
  check('visitor exits',
    (await owner.call('POST', `/visitors/${visitorId}/exit`)).status === 200)

  const complaint = await owner.call('POST', '/complaints', {
    resident_id: residentId, branch_id: branchId, category: 'Plumbing',
    subject: 'Shower runs cold', description: 'No hot water after 7am.',
  })
  check('complaint raised', complaint.status === 201)
  const complaintId = complaint.body?.data?.id
  check('complaint resolved',
    (await owner.call('PATCH', `/complaints/${complaintId}`,
      { status: 'RESOLVED', resolution: 'Thermostat replaced' })).status === 200)

  const search = await owner.call('GET', '/search?q=Arjun')
  check('global search finds the resident',
    (search.body?.data?.results || []).some((r) => r.type === 'resident'))

  // ------------------------------------------------------ 8. resident portal
  section('8. Resident portal')
  const tenant = makeClient()
  const tenantLogin = await login(tenant, `arjun.${unique}@e2e-pgguru.com`, residentPassword)
  check('resident signs in', tenantLogin.status === 200, `status ${tenantLogin.status}`)

  if (tenantLogin.status === 200) {
    const home = await tenant.call('GET', '/me/home')
    check('resident sees their own placement',
      home.body?.data?.placement?.room === '101')

    const profile = await tenant.call('GET', '/me/profile')
    check('resident profile loads', profile.status === 200)

    const rent = await tenant.call('GET', '/me/rent')
    check('resident sees their own rent', rent.status === 200)

    const theirComplaints = await tenant.call('GET', '/me/complaints')
    check('resident sees their complaint status',
      (theirComplaints.body?.data || []).some((c) => c.status === 'RESOLVED'))

    // ------------------------------------------ 9. unauthorised access
    section('9. Unauthorised access is refused')
    check('resident cannot list all residents',
      (await tenant.call('GET', '/residents')).status === 403)
    check('resident cannot read the audit log',
      (await tenant.call('GET', '/audit')).status === 403)
    check('resident cannot search',
      (await tenant.call('GET', '/search?q=Arjun')).status === 403)
    check('resident cannot reach master settings',
      (await tenant.call('GET', '/master/settings')).status === 403)
  }

  const anon = makeClient()
  check('anonymous cannot list residents',
    (await anon.call('GET', '/residents', undefined, { auth: false })).status === 401)
  check('anonymous cannot read plans',
    (await anon.call('GET', '/meta/plans', undefined, { auth: false })).status === 401)

  // ----------------------------------------------------- 10. session
  section('10. Session lifecycle')
  const refreshed = await owner.call('POST', '/auth/refresh', {})
  check('refresh works from the cookie alone', refreshed.status === 200)
  check('refresh response carries no refresh token',
    !JSON.stringify(refreshed.body).includes('refresh_token'))
  if (refreshed.status === 200) owner.setToken(refreshed.body.data.access_token)

  const loggedOut = await owner.call('POST', '/auth/logout', {})
  check('logout succeeds', loggedOut.status === 200)
  check('refresh after logout is refused',
    (await owner.call('POST', '/auth/refresh', {})).status === 401)

} catch (err) {
  failed++
  failures.push(`unexpected error: ${err.message}`)
  console.error('\n', err)
}

/* --------------------------------------------------------------- report */
console.log(`\n${'─'.repeat(58)}`)
console.log(`E2E critical path: \x1b[32m${passed} passed\x1b[0m, ` +
            `${failed ? `\x1b[31m${failed} failed\x1b[0m` : '0 failed'}`)
if (failures.length) {
  console.log('\nFailures:')
  failures.forEach((f) => console.log(`  - ${f}`))
}
console.log('─'.repeat(58))

shutdown(failed ? 1 : 0)
