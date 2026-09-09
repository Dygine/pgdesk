/** Roles and the permission catalogue. */
import { api, unwrap } from './client'

export const roleApi = {
  list: () => api.get('/roles').then(unwrap),
  get: (id) => api.get(`/roles/${id}`).then(unwrap),
  create: (body) => api.post('/roles', body).then(unwrap),
  update: (id, body) => api.patch(`/roles/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/roles/${id}`).then(unwrap),
}

export const permissionApi = {
  catalog: () => api.get('/permissions').then(unwrap),
}
