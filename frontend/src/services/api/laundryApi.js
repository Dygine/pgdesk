/** Laundry slots and requests. */
import { api, unwrap, unwrapList } from './client'

export const laundryApi = {
  slots: (params) => api.get('/laundry/slots', params).then(unwrap),
  createSlot: (body) => api.post('/laundry/slots', body).then(unwrap),
  book: (body) => api.post('/laundry/bookings', body).then(unwrap),
  requests: (params) => api.get('/laundry/requests', params).then(unwrapList),
  setStatus: (id, status) =>
    api.patch(`/laundry/requests/${id}`, { status }).then(unwrap),
}
