/** Plans, subscriptions and platform-wide usage. */
import { api, unwrap } from './client'

export const subscriptionApi = {
  plans: () => api.get('/master/plans').then(unwrap),
  updatePlan: (id, body) => api.patch(`/master/plans/${id}`, body).then(unwrap),
  list: () => api.get('/master/subscriptions').then(unwrap),
  sweep: () => api.post('/master/subscriptions/sweep').then(unwrap),
  usage: (severity) => api.get('/master/usage', { severity }).then(unwrap),
  /** The signed-in tenant's own plan and usage. */
  mine: () => api.get('/subscription').then(unwrap),
}
