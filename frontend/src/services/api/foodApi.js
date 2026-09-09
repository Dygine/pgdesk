/** Mess menu and meal attendance. */
import { api, unwrap } from './client'

export const foodApi = {
  menus: (params) => api.get('/food/menus', params).then(unwrap),
  saveMenu: (body) => api.put('/food/menus', body).then(unwrap),
  markMeal: (body) => api.post('/food/meals', body).then(unwrap),
  counts: (params) => api.get('/food/counts', params).then(unwrap),
}
