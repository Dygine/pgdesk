/** Payments and their verification. */
import { api, unwrap, unwrapList } from './client'

export const paymentApi = {
  list: (params) => api.get('/payments', params).then(unwrapList),
  create: (body) => api.post('/payments', body).then(unwrap),
  /** Only verification moves an invoice balance. */
  verify: (id, approved, note) =>
    api.post(`/payments/${id}/verify`, { approved, note }).then(unwrap),
  refund: (id, reason) => api.post(`/payments/${id}/refund`, { reason }).then(unwrap),
}
