/** Resident and staff attendance. */
import { api, unwrap, unwrapList } from './client'

export const attendanceApi = {
  list: (params) => api.get('/attendance', params).then(unwrapList),
  mark: (body) => api.post('/attendance', body).then(unwrap),
}
