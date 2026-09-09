/** Inventory and its stock ledger. */
import { api, unwrap, unwrapList } from './client'

export const inventoryApi = {
  list: (params) => api.get('/inventory', params).then(unwrapList),
  create: (body) => api.post('/inventory', body).then(unwrap),
  /** txn_type: STOCK_IN | STOCK_OUT | ADJUSTMENT | TRANSFER */
  adjust: (id, body) => api.post(`/inventory/${id}/adjust`, body).then(unwrap),
  transactions: (id) => api.get(`/inventory/${id}/transactions`).then(unwrap),
}
