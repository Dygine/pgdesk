/** Staff users and their branch assignments. */
import { api, unwrap, unwrapList } from './client'

export const userApi = {
  list: (params) => api.get('/users', params).then(unwrapList),
  get: (id) => api.get(`/users/${id}`).then(unwrap),
  create: (body) => api.post('/users', body).then(unwrap),
  update: (id, body) => api.patch(`/users/${id}`, body).then(unwrap),
  deactivate: (id) => api.delete(`/users/${id}`).then(unwrap),
  resetPassword: (id) => api.post(`/users/${id}/reset-password`).then(unwrap),

  branches: (id) => api.get(`/user-branches/${id}`).then(unwrap),
  setBranches: (id, branch_ids) =>
    api.put(`/user-branches/${id}`, { branch_ids }).then(unwrap),
}
