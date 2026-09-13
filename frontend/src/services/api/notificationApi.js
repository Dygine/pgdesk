/** Notifications. Always scoped to the caller by the API, never by a parameter. */
import { api, unwrap, unwrapList } from './client'

export const notificationApi = {
  list: (params) => api.get('/notifications', params),
  markRead: (id) => api.post(`/notifications/${id}/read`).then(unwrap),
  markAllRead: () => api.post('/notifications/read-all').then(unwrap),

  // Push. Registration is repeated on every app start rather than once at
  // first permission: Firebase rotates tokens on its own schedule, and a stale
  // one fails silently - notifications simply stop, with nothing to see.
  registerDevice: (body) => api.post('/notifications/device', body).then(unwrap),
  revokeDevice: (body) => api.post('/notifications/device/revoke', body).then(unwrap),
}
