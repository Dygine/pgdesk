/** Simple accounts: the profit and loss statement. */
import { api, unwrap, BASE_URL, tokenStore } from './client'

export const accountsApi = {
  pnl: (params) => api.get('/accounts/pnl', params).then(unwrap),

  /** Same pattern as reportApi.downloadCsv: an authenticated fetch, saved as a file. */
  async downloadCsv(params = {}) {
    const url = new URL(`${BASE_URL.replace(/\/$/, '')}/accounts/pnl/export`)
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== 'all') url.searchParams.set(k, v)
    })
    const res = await fetch(url, { headers: { Authorization: `Bearer ${tokenStore.accessToken}` } })
    if (!res.ok) throw new Error('The statement could not be exported.')
    const blob = await res.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `pgguru-profit-and-loss-${params.from_date || ''}-${params.to_date || ''}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  },
}
