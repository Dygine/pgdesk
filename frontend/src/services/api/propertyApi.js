/** Buildings, floors, rooms, beds and the nested blueprint. */
import { api, unwrap, unwrapList } from './client'

export const buildingApi = {
  list: (params) => api.get('/buildings', params).then(unwrap),
  create: (body) => api.post('/buildings', body).then(unwrap),
  update: (id, body) => api.patch(`/buildings/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/buildings/${id}`).then(unwrap),
}

export const floorApi = {
  list: (params) => api.get('/floors', params).then(unwrap),
  create: (body) => api.post('/floors', body).then(unwrap),
  update: (id, body) => api.patch(`/floors/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/floors/${id}`).then(unwrap),
}

export const roomApi = {
  list: (params) => api.get('/rooms', params).then(unwrapList),
  get: (id) => api.get(`/rooms/${id}`).then(unwrap),
  create: (body) => api.post('/rooms', body).then(unwrap),
  update: (id, body) => api.patch(`/rooms/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/rooms/${id}`).then(unwrap),
}

export const bedApi = {
  list: (params) => api.get('/beds', params).then(unwrapList),
  create: (body) => api.post('/beds', body).then(unwrap),
  update: (id, body) => api.patch(`/beds/${id}`, body).then(unwrap),
  setStatus: (id, status) => api.patch(`/beds/${id}`, { status }).then(unwrap),
  remove: (id) => api.delete(`/beds/${id}`).then(unwrap),
}

export const propertyApi = {
  blueprint: (branch_id) => api.get('/property/blueprint', { branch_id }).then(unwrap),
}
