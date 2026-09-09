/** The QR gate. */
import { api, unwrap, unwrapList } from './client'

export const scanApi = {
  /**
   * Always resolves — a refusal comes back as a result with `allowed: false`,
   * because the guard needs to see which resident was refused and why.
   */
  scan: (token, direction, gate) =>
    api.post('/scan', { token, direction, gate }).then(unwrap),
  logs: (params) => api.get('/gate-logs', params).then(unwrapList),
}
