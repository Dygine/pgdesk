/** Announcements. */
import { api, unwrap, unwrapList } from './client'

export const announcementApi = {
  list: (params) => api.get('/announcements', params).then(unwrapList),
  create: (body) => api.post('/announcements', body).then(unwrap),
  update: (id, body) => api.patch(`/announcements/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/announcements/${id}`).then(unwrap),
}
