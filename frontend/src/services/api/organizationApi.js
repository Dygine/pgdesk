/** Master-admin: organisations, plans, subscriptions, usage, audit. */
import { api, unwrap, unwrapList } from './client'

export const organizationApi = {
  list: (params) => api.get('/master/organizations', params).then(unwrapList),
  get: (id) => api.get(`/master/organizations/${id}`).then(unwrap),
  create: (body) => api.post('/master/organizations', body).then(unwrap),
  update: (id, body) => api.patch(`/master/organizations/${id}`, body).then(unwrap),

  setStatus: (id, status, reason) =>
    api.post(`/master/organizations/${id}/status`, { status, reason }).then(unwrap),
  extend: (id, days) => api.post(`/master/organizations/${id}/extend`, { days }).then(unwrap),
  changePlan: (id, plan_code) =>
    api.post(`/master/organizations/${id}/plan`, { plan_code }).then(unwrap),
  setLimits: (id, overrides) =>
    api.post(`/master/organizations/${id}/limits`, { overrides }).then(unwrap),
  usage: (id) => api.get(`/master/organizations/${id}/usage`).then(unwrap),
}

export const masterApi = {
  dashboard: () => api.get('/master/dashboard').then(unwrap),
  audit: (params) => api.get('/master/audit', params).then(unwrapList),
}
