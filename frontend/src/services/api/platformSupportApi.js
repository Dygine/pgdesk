/**
 * Tickets a PG owner raises with the platform, and the operator's queue.
 *
 * Separate from `queryApi`, which is a resident asking their PG owner. Those
 * two run in opposite directions and must not share a module, or a future edit
 * will point one at the other's endpoint.
 */
import { api, unwrap } from './client'

export const platformSupportApi = {
  meta: () => api.get('/support/platform/meta').then(unwrap),
  list: () => api.get('/support/platform').then(unwrap),
  get: (id) => api.get(`/support/platform/${id}`).then(unwrap),
  create: (body) => api.post('/support/platform', body).then(unwrap),
  reply: (id, body) => api.post(`/support/platform/${id}/reply`, { body }).then(unwrap),
  close: (id) => api.post(`/support/platform/${id}/close`).then(unwrap),
}

export const masterTicketApi = {
  queue: (ticket_status) =>
    api.get('/master/tickets', { ticket_status }).then(unwrap),
  get: (id) => api.get(`/master/tickets/${id}`).then(unwrap),
  /** `internal: true` is a note to yourself — the owner never sees it. */
  reply: (id, body) => api.post(`/master/tickets/${id}/reply`, body).then(unwrap),
  setStatus: (id, status) =>
    api.post(`/master/tickets/${id}/status`, { status }).then(unwrap),
}
