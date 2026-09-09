/** Visitor management. */
import { api, unwrap, unwrapList } from './client'

export const visitorApi = {
  list: (params) => api.get('/visitors', params).then(unwrapList),
  create: (body) => api.post('/visitors', body).then(unwrap),
  decide: (id, approved, note) =>
    api.post(`/visitors/${id}/decision`, { approved, note }).then(unwrap),
  entry: (id) => api.post(`/visitors/${id}/entry`).then(unwrap),
  exit: (id) => api.post(`/visitors/${id}/exit`).then(unwrap),
}
