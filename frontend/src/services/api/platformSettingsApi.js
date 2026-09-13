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

  /** How many people a broadcast would reach, before anything is written. */
  broadcastReach: () => api.get('/master/broadcast/reach').then(unwrap),

  /** One message to every app user, across all PGs. Cannot be recalled. */
  broadcast: (body) => api.post('/master/broadcast', body).then(unwrap),

  /** Live delivery and read counts for one broadcast. Polled after sending. */
  broadcastStats: (id) => api.get(`/master/broadcast/${id}/stats`).then(unwrap),

  /** The last few broadcasts, reconstructed from their notification rows. */
  recentBroadcasts: () => api.get('/master/broadcasts').then(unwrap),
}
