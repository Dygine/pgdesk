/** Notifications. Always scoped to the caller by the API, never by a parameter. */
import { api, unwrap, unwrapList } from './client'

export const notificationApi = {
  list: (params) => api.get('/notifications', params),
  markRead: (id) => api.post(`/notifications/${id}/read`).then(unwrap),
  markAllRead: () => api.post('/notifications/read-all').then(unwrap),
}
