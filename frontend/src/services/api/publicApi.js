/**
 * The unauthenticated API, plus the PG-seeker account.
 *
 * Every call here runs with `auth: false`: these endpoints are for people with
 * no staff or resident account, and a stale access token left in memory must
 * not change what a stranger sees. Seeker calls carry their own header instead
 * (`X-PGDesk-Seeker`), which nothing outside /public/seeker/* accepts.
 */
import { api, unwrap } from './client'
import { readSeekerToken } from '@/lib/seekerSession'

const anon = { auth: false }

async function asSeeker() {
  const token = await readSeekerToken()
  return { auth: false, headers: token ? { 'X-PGDesk-Seeker': token } : {} }
}

export const publicApi = {
  /** Listed PGs. With a position it sorts by distance, without one by price. */
  searchPgs: (params) => api.get('/public/pgs', params, anon).then(unwrap),
  getPg: (id) => api.get(`/public/pgs/${id}`, undefined, anon).then(unwrap),

  /* ------------------------------------------------------- area search */
  places: (q) => api.get('/public/places', { q }, anon).then(unwrap),
  reversePlace: (latitude, longitude) =>
    api.get('/public/places/reverse', { latitude, longitude }, anon).then(unwrap),

  /* --------------------------------------------------- email verification */
  sendCode: (email) => api.post('/public/send-code', { email }, anon).then(unwrap),
  verifyCode: (email, code) =>
    api.post('/public/verify-code', { email, code }, anon).then(unwrap),

  /* ---------------------------------------------------------------- write */
  createEnquiry: (body) => api.post('/public/enquiries', body, anon).then(unwrap),
  signupOwner: (body) => api.post('/public/signup/owner', body, anon).then(unwrap),

  /* ------------------------------------------------------- seeker account */
  // 409 `needs_profile` from seekerSession means "no account yet - ask for a
  // name and send the same verification token back".
  seekerSession: (body) => api.post('/public/seeker/session', body, anon).then(unwrap),
  seekerMe: async () => api.get('/public/seeker/me', undefined, await asSeeker()).then(unwrap),
  seekerUpdate: async (body) =>
    api.patch('/public/seeker/me', body, await asSeeker()).then(unwrap),
  seekerLogout: async () => api.post('/public/seeker/logout', {}, await asSeeker()).then(unwrap),
  seekerEnquiries: async () =>
    api.get('/public/seeker/enquiries', undefined, await asSeeker()).then(unwrap),
  seekerEnquire: async (body) =>
    api.post('/public/seeker/enquiries', body, await asSeeker()).then(unwrap),
}
