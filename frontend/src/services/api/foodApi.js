/** Mess menu and meal attendance. */
import { api, unwrap } from './client'

export const foodApi = {
  menus: (params) => api.get('/food/menus', params).then(unwrap),
  saveMenu: (body) => api.put('/food/menus', body).then(unwrap),
  markMeal: (body) => api.post('/food/meals', body).then(unwrap),
  counts: (params) => api.get('/food/counts', params).then(unwrap),
  effective: (params) => api.get('/food/menus/effective', params).then(unwrap),
  deleteSpecial: (id) => api.delete(`/food/menus/${id}`).then(unwrap),
  week: (branchId) => api.get('/food/week', { branch_id: branchId }).then(unwrap),
  saveWeek: (body) => api.put('/food/week', body).then(unwrap),
  schedule: () => api.get('/food/schedule').then(unwrap),
  saveSchedule: (meals) => api.put('/food/schedule', { meals }).then(unwrap),
}
