/**
 * Platform-wide settings. Master admin only; the API 403s anyone else.
 *
 * `channels` in the response reports what can actually deliver on this
 * deployment, which is separate from whether an operator has switched a channel
 * on. The UI must show both rather than collapsing them into one toggle.
 */
import { api, unwrap } from './client'

export const platformSettingsApi = {
  get: () => api.get('/master/settings').then(unwrap),
  update: (body) => api.patch('/master/settings', body).then(unwrap),

  /**
   * Write-only. There is no matching read anywhere in the API - the settings
   * response reports whether a password is stored, never what it is.
   */
  setSmtpPassword: (password) =>
    api.put('/master/settings/smtp-password', { password }).then(unwrap),

  /** Also write-only. The settings response reports whether a key is stored. */
  setBrevoKey: (api_key) =>
    api.put('/master/settings/brevo-key', { api_key }).then(unwrap),

  /** Proves delivery, which is a different claim from "saved". */
  sendTestEmail: (to) =>
    api.post('/master/settings/test-email', { to }).then(unwrap),
}
