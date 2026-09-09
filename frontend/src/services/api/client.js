/**
 * The single place the app talks to the API.
 *
 * Responsibilities: base URL, Authorization header, JSON, the response envelope,
 * and transparent access-token refresh. No component builds a URL or reads a
 * token; they call the small `*Api` modules next to this file.
 *
 * SESSION HANDLING
 * -----------------
 * The refresh token is never seen by JavaScript. The API sets it as an
 * HttpOnly, Secure, SameSite cookie scoped to /api/v1/auth, so a script
 * injected into the page cannot read the long-lived credential and cannot send
 * it anywhere. Every request here uses `credentials: 'include'` so the browser
 * attaches it on the auth calls that need it.
 *
 * The access token is held in a module-scoped variable — memory only, never
 * localStorage. It is short-lived, and on a page reload the session is restored
 * by calling /auth/refresh, which the cookie authenticates. So a refresh still
 * keeps the user signed in without anything durable being written to disk.
 *
 * Everything outside this file goes through `tokenStore`, so the shape of this
 * decision stays contained here.
 */

import { Capacitor } from '@capacitor/core'

/**
 * Where the API lives.
 *
 * On the web an empty VITE_API_URL can fall back to localhost, because
 * localhost is the developer's own machine and that is what they meant.
 *
 * On Android it is not. Inside the APK `localhost` resolves to the handset, so
 * a bundle built without VITE_API_URL produces an app that looks fine, shows a
 * login form, and can never reach anything. That failure is silent and wastes
 * an afternoon, so we make it loud at startup instead: the value is baked in at
 * build time and there is no way to correct it at runtime.
 */
const FALLBACK = 'http://localhost:8000/api/v1'
const CONFIGURED = import.meta.env.VITE_API_URL

if (Capacitor.isNativePlatform()) {
  const url = CONFIGURED || ''
  if (!url || /(^|\/\/)(localhost|127\.0\.0\.1|10\.0\.2\.2)/.test(url)) {
    throw new Error(
      'PGDesk was built without a reachable VITE_API_URL. On a device, ' +
      'localhost is the phone itself. Rebuild with the real API origin: ' +
      'VITE_API_URL=https://api.<your-domain>/api/v1 npm run build:android',
    )
  }
  if (!url.startsWith('https://')) {
    // The refresh cookie is Secure; over http it is never sent and the session
    // dies at the first refresh. Better to say so now than to debug it later.
    throw new Error(
      'PGDesk on Android requires an https API origin. The refresh cookie is ' +
      'Secure + SameSite=None and will not be sent over http.',
    )
  }
}

const BASE_URL = CONFIGURED || FALLBACK

/** Header proving the request came from our own front end — the CSRF factor. */
const CSRF_HEADER = 'X-PGDesk-Auth'

/* ------------------------------------------------------------ token store */
/**
 * In-memory only. Deliberately not localStorage or sessionStorage: both are
 * readable by any script on the page, which is exactly what the HttpOnly cookie
 * exists to avoid. Losing this on reload is fine — `restore()` gets it back.
 */
let accessToken = null

export const tokenStore = {
  write(tokens) { accessToken = tokens?.access_token || null },
  clear() { accessToken = null },
  get accessToken() { return accessToken },
  /**
   * Whether a session might exist. The refresh cookie is HttpOnly so this
   * cannot be answered locally with certainty — only /auth/refresh knows. A
   * true answer here means "worth asking", not "signed in".
   */
  get hasAccessToken() { return Boolean(accessToken) },
}

/**
 * Called when the session cannot be recovered. AuthContext registers a handler
 * so an expired session sends the user to the login screen from anywhere,
 * without every caller having to check.
 */
let onSessionExpired = () => {}
export const setSessionExpiredHandler = (fn) => { onSessionExpired = fn || (() => {}) }

/* ---------------------------------------------------------------- errors */
export class ApiError extends Error {
  constructor(message, { status, code, errors = [] } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.errors = errors
  }
  /** field -> message, for inline form display */
  get fieldErrors() {
    return Object.fromEntries(this.errors.filter((e) => e.field).map((e) => [e.field, e.message]))
  }
  get isAuthError() { return this.status === 401 }
  get isForbidden() { return this.status === 403 }
}

export class NetworkError extends ApiError {
  constructor() {
    super('Could not reach the server. Check that the API is running.', { status: 0, code: 'network' })
    this.name = 'NetworkError'
  }
}

/* --------------------------------------------------------------- fetching */
function buildUrl(path, params) {
  const url = new URL(BASE_URL.replace(/\/$/, '') + path)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== 'all') url.searchParams.set(k, v)
    })
  }
  return url
}

async function parse(res) {
  if (res.status === 204) return null
  try { return await res.json() } catch {
    throw new ApiError('The server sent a response we could not read.', { status: res.status })
  }
}

function toError(payload, status) {
  return new ApiError(payload?.message || 'Something went wrong.', {
    status, code: payload?.code, errors: payload?.errors || [],
  })
}

/** A single in-flight refresh, shared by every request that hits a 401 at once. */
let refreshInFlight = null

export async function refreshAccessToken() {
  // Refresh tokens are single-use server-side, so two parallel refreshes would
  // invalidate each other and sign the user out. Everyone waits on one promise.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(buildUrl('/auth/refresh'), {
          method: 'POST',
          // The body is empty: the token is in the cookie, which the browser
          // attaches because of credentials: 'include'.
          headers: { 'Content-Type': 'application/json', [CSRF_HEADER]: '1' },
          credentials: 'include',
          body: JSON.stringify({}),
        })
        const payload = await parse(res)
        if (!res.ok || payload?.success === false) return false
        tokenStore.write({ access_token: payload.data.access_token })
        return true
      } catch { return false } finally {
        setTimeout(() => { refreshInFlight = null }, 0)
      }
    })()
  }
  return refreshInFlight
}

async function request(path, { method = 'GET', body, params, auth = true, retry = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`
  // Sent on every call so the auth endpoints — the only ones the cookie is
  // scoped to — always carry it.
  headers[CSRF_HEADER] = '1'

  let res
  try {
    res = await fetch(buildUrl(path, params), {
      method, headers,
      credentials: 'include',
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch { throw new NetworkError() }

  const payload = await parse(res)

  if (res.ok && payload?.success !== false) return payload

  /* An expired access token is recoverable exactly once per request. The
     attempt is made even with no access token in memory, because after a page
     reload that is the normal state and the cookie may still be good. */
  if (res.status === 401 && auth && retry) {
    if (await refreshAccessToken()) {
      return request(path, { method, body, params, auth, retry: false })
    }
    tokenStore.clear()
    onSessionExpired()
  }

  throw toError(payload, res.status)
}

export const api = {
  get: (path, params, opts) => request(path, { ...opts, params }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body }),
  put: (path, body, opts) => request(path, { ...opts, method: 'PUT', body }),
  delete: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
}

export const unwrap = (response) => response?.data ?? null
export const unwrapList = (response) => ({
  items: response?.data ?? [],
  pagination: response?.pagination ?? { page: 1, page_size: 20, total: 0, total_pages: 1 },
})

export { BASE_URL }
