/** Support queries. */
import { api, unwrap, unwrapList } from './client'

export const queryApi = {
  list: (params) => api.get('/queries', params).then(unwrapList),
  get: (id) => api.get(`/queries/${id}`).then(unwrap),
  create: (body) => api.post('/queries', body).then(unwrap),
  reply: (id, message, close = false) =>
    api.post(`/queries/${id}/reply`, { message, close }).then(unwrap),
}
