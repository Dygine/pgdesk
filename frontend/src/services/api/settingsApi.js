/** Organisation settings. */
import { api, unwrap } from './client'

export const settingsApi = {
  get: () => api.get('/settings').then(unwrap),
  update: (body) => api.patch('/settings', body).then(unwrap),
}
