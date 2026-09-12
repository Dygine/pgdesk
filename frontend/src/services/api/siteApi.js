/**
 * The public website's content.
 *
 * `content()` is the only call on the marketing page, and it is deliberately
 * anonymous - it runs before anyone has signed in. The rest are the master
 * admin's editor and need a session.
 */
import { api, unwrap } from './client'

const anon = { auth: false }

export const siteApi = {
  /** Published blocks and images. No session required. */
  content: () => api.get('/site', undefined, anon).then(unwrap),

  /** Everything, published or not, with each block's preset alongside it. */
  admin: () => api.get('/master/site').then(unwrap),

  saveBlock: (key, body, isPublished = true) =>
    api.put(`/master/site/blocks/${key}`, { body, is_published: isPublished }).then(unwrap),
  resetBlock: (key) => api.delete(`/master/site/blocks/${key}`).then(unwrap),

  /** Either `url` (hosted elsewhere) or `image` (base64, under 120 KB). */
  saveImage: (payload) => api.put('/master/site/images', payload).then(unwrap),
  deleteImage: (slot) => api.delete(`/master/site/images/${slot}`).then(unwrap),
}
