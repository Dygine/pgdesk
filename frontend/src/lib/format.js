export const inr = (n, opts = {}) => {
  const v = Number(n || 0)
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR',
    minimumFractionDigits: opts.paise ? 2 : 0,
    maximumFractionDigits: opts.paise ? 2 : 0,
  }).format(v)
}

export const num = (n) => new Intl.NumberFormat('en-IN').format(Number(n || 0))

export const pct = (part, total) => (!total ? 0 : Math.round((part / total) * 1000) / 10)

export const dateFmt = (d, style = 'medium') => {
  if (!d) return '—'
  const dt = typeof d === 'string' ? new Date(d) : d
  if (Number.isNaN(dt.getTime())) return '—'
  if (style === 'short') return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
  if (style === 'long') return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })
  return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export const timeFmt = (d) => {
  if (!d) return '—'
  const dt = typeof d === 'string' ? new Date(d) : d
  return dt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
}

export const dateTimeFmt = (d) => `${dateFmt(d)} · ${timeFmt(d)}`

export const iso = (d) => (typeof d === 'string' ? d.slice(0, 10) : d.toISOString().slice(0, 10))
export const today = () => iso(new Date())

export const daysBetween = (a, b) =>
  Math.round((new Date(b).setHours(0, 0, 0, 0) - new Date(a).setHours(0, 0, 0, 0)) / 86400000)

export const relative = (d) => {
  const diff = daysBetween(d, new Date())
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff === -1) return 'Tomorrow'
  if (diff > 1 && diff < 30) return `${diff} days ago`
  if (diff < -1 && diff > -30) return `in ${Math.abs(diff)} days`
  return dateFmt(d)
}

export const initials = (name = '') =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

export const addMonths = (d, n) => {
  const dt = new Date(d)
  dt.setMonth(dt.getMonth() + n)
  return iso(dt)
}

/**
 * "14:00:00" from the API into "2:00 pm".
 *
 * `timeFmt` above takes a full timestamp; a bare time string has no date for
 * `Date` to parse, so it needs its own formatter rather than a hack at the
 * call site.
 */
export const timeOnly = (t) => {
  if (!t) return '—'
  const [h, m] = String(t).split(':').map(Number)
  const suffix = h >= 12 ? 'pm' : 'am'
  const hour = h % 12 === 0 ? 12 : h % 12
  return `${hour}:${String(m || 0).padStart(2, '0')} ${suffix}`
}
