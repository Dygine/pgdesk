/** Reports. Aggregated server-side, exported as CSV. */
import { api, unwrap, BASE_URL, tokenStore } from './client'

export const reportApi = {
  catalogue: () => api.get('/reports').then(unwrap),
  run: (key, params) => api.get(`/reports/${key}`, params).then(unwrap),

  /**
   * CSV comes back as a file rather than JSON, so it bypasses the envelope and
   * is fetched directly with the bearer token attached.
   */
  async downloadCsv(key, params = {}) {
    const url = new URL(`${BASE_URL.replace(/\/$/, '')}/reports/${key}/export`)
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== 'all') url.searchParams.set(k, v)
    })
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${tokenStore.accessToken}` },
    })
    if (!res.ok) throw new Error('That export could not be generated.')
    const blob = await res.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `pgguru-${key}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  },
}
