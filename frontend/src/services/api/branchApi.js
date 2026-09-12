/** Branch CRUD. Scoped server-side to the caller's assigned branches. */
import { api, unwrap, unwrapList } from './client'

export const branchApi = {
  list: (params) => api.get('/branches', params).then(unwrapList),
  create: (body) => api.post('/branches', body).then(unwrap),
  update: (id, body) => api.patch(`/branches/${id}`, body).then(unwrap),
  deactivate: (id) => api.delete(`/branches/${id}`).then(unwrap),

  /** Gate position and geofence. Separate from `update` because it is a
   *  separate decision: an address typo affects paperwork, the geofence
   *  decides whether anyone can mark attendance tomorrow. */
  setLocation: (id, body) => api.put(`/branches/${id}/location`, body).then(unwrap),
  rotateGateToken: (id) => api.post(`/branches/${id}/gate-token`).then(unwrap),

  /** Publishing decisions are their own action, and their own audit line. */
  setListing: (id, body) => api.put(`/branches/${id}/listing`, body).then(unwrap),

  /* --------------------------------------------------------- listing photos */
  /** Up to six, each under 5 KB. The bytes come back as data URLs, so this is
   *  the one branch call that is measurably heavy - call it on the listing
   *  screen, never in a list. */
  photos: (id) => api.get(`/branches/${id}/photos`).then(unwrap),
  addPhoto: (id, body) => api.post(`/branches/${id}/photos`, body).then(unwrap),
  deletePhoto: (id, photoId) => api.delete(`/branches/${id}/photos/${photoId}`).then(unwrap),
  /** Ids in display order. The first one leads the public search card. */
  reorderPhotos: (id, photoIds) =>
    api.put(`/branches/${id}/photos/order`, { photo_ids: photoIds }).then(unwrap),
}
