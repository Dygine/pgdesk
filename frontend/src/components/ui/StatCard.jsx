import { Link } from 'react-router-dom'
import { ArrowUpRight, ArrowDownRight } from 'lucide-react'

const cx = (...a) => a.filter(Boolean).join(' ')

const ACCENT = {
  brand: 'bg-brand-50 text-brand-700', emerald: 'bg-emerald-50 text-emerald-600',
  amber: 'bg-amber-50 text-amber-600', rose: 'bg-rose-50 text-rose-600',
  blue: 'bg-blue-50 text-blue-600', slate: 'bg-slate-100 text-slate-600',
  violet: 'bg-violet-50 text-violet-600', teal: 'bg-teal-50 text-teal-600',
}

export function StatCard({ label, value, sub, icon: Icon, tone = 'brand', delta, to, footer, className }) {
  const Wrapper = to ? Link : 'div'
  return (
    <Wrapper {...(to ? { to } : {})}
      className={cx('card p-4 flex flex-col gap-3 transition-shadow min-w-0', to && 'hover:shadow-lift', className)}>
      <div className="flex items-start justify-between gap-2 min-w-0">
        {/* min-w-0 on both: without it the card's content min-width becomes the
            floor for its grid track, and a 3-up row of these pushes the page
            wider than a 360px viewport. */}
        <p className="text-[13px] font-medium text-slate-500 leading-tight min-w-0">{label}</p>
        {Icon && (
          <span className={cx('h-8 w-8 rounded-lg inline-flex items-center justify-center shrink-0', ACCENT[tone])}>
            <Icon size={16} />
          </span>
        )}
      </div>
      <div>
        <p className="text-[26px] leading-none font-semibold text-slate-900 tnum">{value}</p>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          {delta != null && (
            <span className={cx('inline-flex items-center gap-0.5 text-xs font-medium tnum',
              delta >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
              {delta >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
              {Math.abs(delta)}%
            </span>
          )}
          {sub && <span className="text-xs text-slate-500">{sub}</span>}
        </div>
      </div>
      {footer}
    </Wrapper>
  )
}

/** Compact variant for dense rows (dashboards with 6+ numbers). */
export function MiniStat({ label, value, tone = 'slate', className }) {
  const dot = { brand: 'bg-brand-500', emerald: 'bg-emerald-500', amber: 'bg-amber-500',
    rose: 'bg-rose-500', blue: 'bg-blue-500', slate: 'bg-slate-400' }[tone]
  return (
    <div className={cx('flex items-center gap-2.5 min-w-0', className)}>
      <span className={cx('h-2 w-2 rounded-full shrink-0', dot)} />
      <div className="min-w-0">
        <p className="text-lg font-semibold text-slate-900 leading-tight tnum">{value}</p>
        <p className="text-xs text-slate-500 truncate">{label}</p>
      </div>
    </div>
  )
}
