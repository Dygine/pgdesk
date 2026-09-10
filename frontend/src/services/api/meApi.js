/**
 * The resident portal.
 *
 * No endpoint here takes a resident id: the API derives it from the token, so
 * there is nothing for the client to get wrong or an attacker to tamper with.
 */
import { api, unwrap } from './client'

export const meApi = {
  home: () => api.get('/me/home').then(unwrap),
  profile: () => api.get('/me/profile').then(unwrap),
  rent: () => api.get('/me/rent').then(unwrap),
  attendance: (days) => api.get('/me/attendance', { days }).then(unwrap),
  qr: () => api.get('/me/qr').then(unwrap),

  /**
   * Advisory: whether this position would be accepted, and why not.
   * The scan itself re-checks everything, so a client that lies here gains
   * nothing beyond a button that looks enabled.
   */
  gateStatus: (params) => api.get('/me/gate', params).then(unwrap),
  selfScan: (body) => api.post('/me/scan', body).then(unwrap),

  food: (days) => api.get('/me/food', { days }).then(unwrap),
  setMeal: (body) => api.post('/me/food/opt', body).then(unwrap),

  laundry: () => api.get('/me/laundry').then(unwrap),
  bookLaundry: (body) => api.post('/me/laundry/book', body).then(unwrap),
  cancelLaundry: (id) => api.post(`/me/laundry/${id}/cancel`).then(unwrap),

  complaints: () => api.get('/me/complaints').then(unwrap),
  raiseComplaint: (body) => api.post('/me/complaints', body).then(unwrap),

  queries: () => api.get('/me/queries').then(unwrap),
  ask: (body) => api.post('/me/queries', body).then(unwrap),
  replyToQuery: (id, message) => api.post(`/me/queries/${id}/reply`, { message }).then(unwrap),

  visitors: () => api.get('/me/visitors').then(unwrap),
  requestVisitor: (body) => api.post('/me/visitors', body).then(unwrap),

  gatePasses: () => api.get('/me/gate-passes').then(unwrap),
  requestGatePass: (body) => api.post('/me/gate-passes', body).then(unwrap),

  announcements: () => api.get('/me/announcements').then(unwrap),
}
