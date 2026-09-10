/**
 * The unauthenticated API.
 *
 * Every call here runs with `auth: false`. Not because a token would be
 * rejected, but because sending one would be wrong: these endpoints exist for
 * people who have no account, and a stale token left in memory from a previous
 * session must not change what a stranger sees.
 */
import { api, unwrap } from './client'

const anon = { auth: false }

export const publicApi = {
  /**
   * Listed PGs. Everything is optional - with a position it sorts by distance,
   * without one it sorts by price.
   */
  searchPgs: (params) => api.get('/public/pgs', params, anon).then(unwrap),
  getPg: (id) => api.get(`/public/pgs/${id}`, undefined, anon).then(unwrap),

  /* --------------------------------------------------- email verification */
  // Shared by signup and enquiry. Deliberately does not reveal whether the
  // address already has an account; signup reports that at submission, where
  // the person can act on it.
  sendCode: (email) => api.post('/public/send-code', { email }, anon).then(unwrap),
  verifyCode: (email, code) =>
    api.post('/public/verify-code', { email, code }, anon).then(unwrap),

  /* ---------------------------------------------------------------- write */
  createEnquiry: (body) => api.post('/public/enquiries', body, anon).then(unwrap),
  signupOwner: (body) => api.post('/public/signup/owner', body, anon).then(unwrap),
}
