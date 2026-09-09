/**
 * Authentication calls. The only module that writes to the token store.
 *
 * The refresh token is an HttpOnly cookie and is never touched here — the
 * browser attaches it to /auth/* on its own. This module only ever handles the
 * short-lived access token, which lives in memory.
 */
import { api, refreshAccessToken, tokenStore, unwrap } from './client'

export const authApi = {
  async login(email, password) {
    // auth:false — there is no token yet, and sending a stale one would be wrong.
    const res = await api.post('/auth/login', { email, password }, { auth: false })
    const { access_token, user } = res.data
    tokenStore.write({ access_token })
    return user
  },

  me: () => api.get('/auth/me').then(unwrap),

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
    }
  },

  /** Sign out everywhere — used after a password change or a lost device. */
  async logoutEverywhere() {
    try {
      await api.post('/auth/logout', { all_sessions: true }, { retry: false })
    } finally {
      tokenStore.clear()
    }
  },

  changePassword: (current_password, new_password) =>
    api.post('/auth/change-password', { current_password, new_password }),
}
