/**
 * Audit log.
 *
 * Two endpoints, because there are two audiences with different rights:
 *
 *   /audit         the tenant's own trail, gated on `audit.view` and filtered
 *                  to the caller's branches
 *   /master/audit  every organisation, master admins only
 *
 * The org-portal page previously called the master route, so it answered 403
 * for exactly the PG owners it was built for.
 */
import { api, unwrapList } from './client'

export const auditApi = {
  list: (params) => api.get('/audit', params).then(unwrapList),
  platform: (params) => api.get('/master/audit', params).then(unwrapList),
}
