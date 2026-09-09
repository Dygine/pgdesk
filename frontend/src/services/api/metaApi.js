/**
 * The first two endpoints the backend exposes. Not wired into any page yet.
 *
 * When Milestone 10 reaches them these replace the hardcoded copies in
 * src/data/permissions.js and src/data/plans.js, which is what stops the
 * frontend and backend permission lists from drifting apart.
 */
import { api, unwrap } from './client'

export const metaApi = {
  permissions: () => api.get('/meta/permissions').then(unwrap),
  plans: () => api.get('/meta/plans').then(unwrap),
}
