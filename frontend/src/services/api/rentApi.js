/** Rent generation and the collection dashboard. */
import { api, unwrap } from './client'

export const rentApi = {
  summary: (params) => api.get('/rent/summary', params).then(unwrap),
  /** Idempotent per resident per month. */
  generate: (body) => api.post('/rent/generate', body || {}).then(unwrap),
  applyLateFees: () => api.post('/rent/late-fees').then(unwrap),
}
