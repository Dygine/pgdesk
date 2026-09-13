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

  /**
   * The Firebase service account key. Write-only, like the two secrets above.
   *
   * Passing null clears it, which is how push is turned off completely -
   * distinct from leaving the field untouched, which keeps the stored key.
   */
  setFcmCredentials: (credentials, project_id) =>
    api.put('/master/settings/fcm-credentials', { credentials, project_id })
      .then(unwrap),

  /** Delivers to the caller's own phones, bypassing the queue. */
  sendTestPush: () => api.post('/master/settings/test-push').then(unwrap),

  /**
   * Drain the queue now rather than waiting for the next sweep. For the case
   * where an operator has just fixed a broken key and wants the backlog out.
   */
  dispatchPush: () => api.post('/master/settings/push-dispatch').then(unwrap),
}
