/**
 * Global search.
 *
 * The API decides what the caller may see - each entity is gated by its own
 * module permission and filtered to the caller's branches - so there is nothing
 * to filter here. The client's only job is to not ask too often.
 */
import { api, unwrap } from './client'

export const searchApi = {
  search: (q, { limit = 5, types } = {}) =>
    api.get('/search', { q, limit, types: types?.join(',') }).then(unwrap),
}
