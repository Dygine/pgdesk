/**
 * Refuse to build an Android bundle that cannot work.
 *
 * VITE_API_URL is baked into the bundle and cannot be changed afterwards, so a
 * mistake here ships as an APK that installs, launches, shows a login form and
 * can never reach anything. client.js catches this at runtime, but a build-time
 * failure is cheaper than finding out on a handset.
 *
 * Run by `npm run build:android`.
 */
const url = process.env.VITE_API_URL
const seed = process.env.VITE_SHOW_SEED_ACCOUNTS

const die = (msg) => {
  console.error(`\n  Android build refused.\n\n  ${msg}\n`)
  console.error('  Example:\n')
  console.error('    VITE_API_URL=https://api.yourdomain.com/api/v1 npm run build:android\n')
  process.exit(1)
}

if (!url) {
  die('VITE_API_URL is not set. On a device "localhost" is the phone itself,\n' +
      '  so there is no sensible default.')
}

let parsed
try { parsed = new URL(url) } catch {
  die(`VITE_API_URL is not a valid URL: ${url}`)
}

if (parsed.protocol !== 'https:') {
  die(`VITE_API_URL must be https. Got "${parsed.protocol}//".\n` +
      '  The refresh cookie is Secure + SameSite=None and is never sent over http,\n' +
      '  so the session would die at the first token refresh.')
}

if (/^(localhost|127\.0\.0\.1|10\.0\.2\.2|0\.0\.0\.0|\[::1\])$/i.test(parsed.hostname)) {
  die(`VITE_API_URL points at "${parsed.hostname}", which on a device means the\n` +
      '  handset itself. Use a hostname the phone can actually reach.')
}

// Placeholders that have appeared in this repository's documentation. Shipping
// one produces an app that fails DNS on first use.
if (/(^|\.)example\.(com|org|net)$/i.test(parsed.hostname) || parsed.hostname.endsWith('.invalid')) {
  die(`VITE_API_URL still uses the documentation placeholder "${parsed.hostname}".\n` +
      '  Replace it with your real API domain.')
}

if (seed === 'true') {
  die('VITE_SHOW_SEED_ACCOUNTS=true would ship working demo credentials inside\n' +
      '  the APK. Unset it, or set it to anything other than "true".')
}

console.log(`  API origin : ${parsed.origin}${parsed.pathname.replace(/\/$/, '')}`)
console.log('  seed accounts: excluded')
console.log('  checks passed — building\n')
