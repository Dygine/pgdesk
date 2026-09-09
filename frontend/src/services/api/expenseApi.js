/** Expenses. */
import { api, unwrap, unwrapList } from './client'

export const expenseApi = {
  list: (params) => api.get('/expenses', params).then(unwrapList),
  summary: (branch_id) => api.get('/expenses/summary', { branch_id }).then(unwrap),
  create: (body) => api.post('/expenses', body).then(unwrap),
  update: (id, body) => api.patch(`/expenses/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/expenses/${id}`).then(unwrap),
}
