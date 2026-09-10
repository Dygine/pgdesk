/**
 * Authentication calls. The only module that writes to the token store.
 *
 * The refresh token is an HttpOnly cookie and is never touched here — the
 * browser attaches it to /auth/* on its own. This module only ever handles the
 * short-lived access token, which lives in memory.
 */
import { api, refreshAccessToken, tokenStore, unwrap } from './client'
import { clearRefreshToken, writeRefreshToken } from '@/lib/nativeSession'

export const authApi = {
  async login(email, password) {
    // auth:false — there is no token yet, and sending a stale one would be wrong.
    const res = await api.post('/auth/login', { email, password }, { auth: false })
    const { access_token, refresh_token, user } = res.data
    tokenStore.write({ access_token })
    // Present only on native, where the server hands the token to the app to
    // keep because the cookie cannot reach it. On the web this is undefined and
    // the call is a no-op.
    if (refresh_token) await writeRefreshToken(refresh_token)
    return user
  },

  me: () => api.get('/auth/me').then(unwrap),

  /* ------------------------------------------------------ password reset */
  // Always resolves for a well-formed address, whether or not an account
  // exists — the API answers identically on purpose, so the UI must not try to
  // infer anything from success here.
  forgotPassword: (email) =>
    api.post('/auth/forgot-password', { email }, { auth: false }).then(unwrap),
  verifyOtp: (email, code) =>
    api.post('/auth/verify-otp', { email, code }, { auth: false }).then(unwrap),
  resetPassword: (verification_token, new_password) =>
    api.post('/auth/reset-password', { verification_token, new_password },
             { auth: false }).then(unwrap),

  /**
   * Rebuild the session after a page reload.
   *
   * The access token was in memory and is gone, but the refresh cookie survived
   * the reload. Asking the API is the only way to find out whether it is still
   * valid — HttpOnly means the client genuinely cannot know on its own.
   */
  restore: () => refreshAccessToken(),

  async logout() {
    try {
      // Best effort: revoke server-side so the refresh token dies with the
      // session, and clear the cookie. The body is empty; the cookie identifies
      // which session to end.
      await api.post('/auth/logout', {}, { retry: false })
    } catch {
      // Already expired or the API is down. The local session still clears.
    } finally {
      tokenStore.clear()
      // Signing out has to remove the stored token too, or the next launch
      // would silently restore the session the user just ended.
      await clearRefreshToken()
    }
  },

  /** Sign out everywhere — used after a password change or a lost device. */
  async logoutEverywhere() {
    try {
      await api.post('/auth/logout', { all_sessions: true }, { retry: false })
    } finally {
      tokenStore.clear()
      await clearRefreshToken()
    }
  },

  changePassword: (current_password, new_password) =>
    api.post('/auth/change-password', { current_password, new_password }),
}
