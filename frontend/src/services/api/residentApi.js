/** Residents, KYC and the bed lifecycle. */
import { api, unwrap, unwrapList } from './client'

export const residentApi = {
  list: (params) => api.get('/residents', params).then(unwrapList),
  get: (id) => api.get(`/residents/${id}`).then(unwrap),
  create: (body) => api.post('/residents', body).then(unwrap),
  update: (id, body) => api.patch(`/residents/${id}`, body).then(unwrap),

  availableBeds: (branch_id, for_resident) =>
    api.get('/residents/available-beds', { branch_id, for_resident }).then(unwrap),
  assignBed: (id, bed_id) => api.post(`/residents/${id}/assign-bed`, { bed_id }).then(unwrap),
  /* Bed, terms and the first invoice in one transaction — see the endpoint. */
  checkIn: (id, body) => api.post(`/residents/${id}/check-in`, body).then(unwrap),
  reserveBed: (id, bed_id) => api.post(`/residents/${id}/reserve-bed`, { bed_id }).then(unwrap),
  transfer: (id, bed_id, reason) =>
    api.post(`/residents/${id}/transfer`, { bed_id, reason }).then(unwrap),
  checkout: (id, body) => api.post(`/residents/${id}/checkout`, body || {}).then(unwrap),
  reissueQr: (id) => api.post(`/residents/${id}/reissue-qr`).then(unwrap),

  /* App access. Responses carry `credentials`: a 30-minute sign-in QR and,
     when a password was issued, the temporary password (shown once). */
  grantPortalAccess: (id, email) =>
    api.post(`/residents/${id}/portal-access`, email ? { email } : {}).then(unwrap),
  resetPortalPassword: (id) => api.post(`/residents/${id}/reset-password`).then(unwrap),
  loginCode: (id) => api.post(`/residents/${id}/login-code`).then(unwrap),
  revokePortalAccess: (id) => api.delete(`/residents/${id}/portal-access`).then(unwrap),

  kyc: (id) => api.get(`/residents/${id}/kyc`).then(unwrap),
  addKyc: (id, body) => api.post(`/residents/${id}/kyc`, body).then(unwrap),
  verifyKyc: (kycId, approved, notes) =>
    api.post(`/residents/kyc/${kycId}/verify`, { approved, notes }).then(unwrap),
}
