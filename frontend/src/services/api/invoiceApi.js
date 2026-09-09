/** Invoices. */
import { api, unwrap, unwrapList } from './client'

export const invoiceApi = {
  list: (params) => api.get('/invoices', params).then(unwrapList),
  get: (id) => api.get(`/invoices/${id}`).then(unwrap),
  create: (body) => api.post('/invoices', body).then(unwrap),
  update: (id, body) => api.patch(`/invoices/${id}`, body).then(unwrap),
  cancel: (id, reason) => api.post(`/invoices/${id}/cancel`, { reason }).then(unwrap),
}
