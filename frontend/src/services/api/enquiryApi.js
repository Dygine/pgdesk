/** Enquiries from people looking for a bed. Tenant-scoped server-side. */
import { api, unwrap, unwrapList } from './client'

export const enquiryApi = {
  list: (params) => api.get('/enquiries', params).then(unwrapList),
  update: (id, body) => api.patch(`/enquiries/${id}`, body).then(unwrap),
}
