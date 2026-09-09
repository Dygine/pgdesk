/** Complaints and their threads. */
import { api, unwrap, unwrapList } from './client'

export const complaintApi = {
  list: (params) => api.get('/complaints', params).then(unwrapList),
  get: (id) => api.get(`/complaints/${id}`).then(unwrap),
  categories: () => api.get('/complaints/categories').then(unwrap),
  create: (body) => api.post('/complaints', body).then(unwrap),
  update: (id, body) => api.patch(`/complaints/${id}`, body).then(unwrap),
}
