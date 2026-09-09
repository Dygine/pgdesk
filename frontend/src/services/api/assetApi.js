/** Assets. */
import { api, unwrap, unwrapList } from './client'

export const assetApi = {
  list: (params) => api.get('/assets', params).then(unwrapList),
  create: (body) => api.post('/assets', body).then(unwrap),
  update: (id, body) => api.patch(`/assets/${id}`, body).then(unwrap),
}
