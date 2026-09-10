/** The workforce list and salaries. Login accounts are userApi, not this. */
import { api, unwrap } from './client'

export const staffApi = {
  list: (params) => api.get('/staff', params).then(unwrap),
  get: (id) => api.get(`/staff/${id}`).then(unwrap),
  create: (body) => api.post('/staff', body).then(unwrap),
  update: (id, body) => api.patch(`/staff/${id}`, body).then(unwrap),
  paySalary: (id, body) => api.post(`/staff/${id}/salary`, body).then(unwrap),
}
