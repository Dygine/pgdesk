/**
 * How residents pay this PG. The Razorpay secrets are write-only: the API says
 * whether one is stored and never returns it. Send "" to remove one, leave the
 * field out to keep it.
 */
import { api, unwrap } from './client'

export const paymentSettingsApi = {
  get: () => api.get('/payment-settings').then(unwrap),
  update: (body) => api.put('/payment-settings', body).then(unwrap),
  testRazorpay: () => api.post('/payment-settings/test-razorpay').then(unwrap),
}
