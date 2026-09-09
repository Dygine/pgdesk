/** Branch CRUD. Scoped server-side to the caller's assigned branches. */
import { api, unwrap, unwrapList } from './client'

export const branchApi = {
  list: (params) => api.get('/branches', params).then(unwrapList),
  create: (body) => api.post('/branches', body).then(unwrap),
  update: (id, body) => api.patch(`/branches/${id}`, body).then(unwrap),
  deactivate: (id) => api.delete(`/branches/${id}`).then(unwrap),
}
