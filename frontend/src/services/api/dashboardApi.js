/** Owner / staff dashboard, scoped server-side to assigned branches. */
import { api, unwrap } from './client'

export const dashboardApi = {
  overview: (branch_id) => api.get('/dashboard', { branch_id }).then(unwrap),
}
