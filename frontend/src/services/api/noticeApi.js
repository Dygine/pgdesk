/** Checkout notices, from the office side. Residents use meApi.giveNotice. */
import { api, unwrap } from './client'

export const noticeApi = {
  list: (params) => api.get('/checkout-notices', params).then(unwrap),
  acknowledge: (id, body) => api.post(`/checkout-notices/${id}/acknowledge`, body || {}).then(unwrap),
  cancel: (id, body) => api.post(`/checkout-notices/${id}/cancel`, body || {}).then(unwrap),
  record: (residentId, body) => api.post(`/residents/${residentId}/checkout-notice`, body).then(unwrap),
}
