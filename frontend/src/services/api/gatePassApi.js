/** Gate passes. */
import { api, unwrap, unwrapList } from './client'

export const gatePassApi = {
  list: (params) => api.get('/gate-passes', params).then(unwrapList),
  create: (body) => api.post('/gate-passes', body).then(unwrap),
  decide: (id, approved, note) =>
    api.post(`/gate-passes/${id}/decision`, { approved, note }).then(unwrap),
  setStatus: (id, status) =>
    api.patch(`/gate-passes/${id}/status`, { status }).then(unwrap),
}
