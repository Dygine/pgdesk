import { useId } from 'react'

const cx = (...a) => a.filter(Boolean).join(' ')
const PALETTE = ['#373DA6', '#0F766E', '#B45309', '#BE185D', '#7C3AED', '#0369A1']

export function ChartCard({ title, subtitle, action, children, className, footer }) {
  return (
    <div className={cx('card flex flex-col', className)}>
      <div className="flex items-start justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-line">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="p-4 sm:p-5 flex-1">{children}</div>
      {footer && <div className="px-4 sm:px-5 py-3 border-t border-line bg-slate-50/60 rounded-b-xl">{footer}</div>}
    </div>
  )
}

/** Vertical bars. Scales to its container — no fixed pixel width anywhere. */
export function BarChart({ data, height = 180, valueFormat = (v) => v, color = '#373DA6', stacked }) {
  const max = Math.max(1, ...data.map((d) => (stacked ? (d.a || 0) + (d.b || 0) : d.value)))
  return (
    <div>
      <div className="flex items-end gap-1.5 sm:gap-2.5" style={{ height }}>
        {data.map((d, i) => {
          const total = stacked ? (d.a || 0) + (d.b || 0) : d.value
          return (
            <div key={i} className="flex-1 min-w-0 flex flex-col justify-end items-center gap-1.5 group relative">
              <span className="text-2xs text-slate-500 tnum opacity-0 group-hover:opacity-100 transition-opacity absolute -top-1 whitespace-nowrap bg-white px-1 rounded">
                {valueFormat(total)}
              </span>
              <div className="w-full flex flex-col justify-end origin-bottom animate-growY"
                style={{ height: `${(total / max) * 100}%`, minHeight: total > 0 ? 3 : 0, animationDelay: `${i * 28}ms` }}>
                {stacked ? (
                  <>
                    <div className="w-full rounded-t-[3px]" style={{ height: `${((d.b || 0) / Math.max(total, 1)) * 100}%`, backgroundColor: '#CBD5E1' }} />
                    <div className="w-full" style={{ height: `${((d.a || 0) / Math.max(total, 1)) * 100}%`, backgroundColor: color }} />
                  </>
                ) : (
                  <div className="w-full h-full rounded-t-[3px] transition-opacity group-hover:opacity-80"
                    style={{ backgroundColor: d.color || color }} />
                )}
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex gap-1.5 sm:gap-2.5 mt-2">
        {data.map((d, i) => (
          <span key={i} className="flex-1 min-w-0 text-center text-2xs text-slate-500 truncate">{d.label}</span>
        ))}
      </div>
    </div>
  )
}

/** Area + line. Uses a gradient fill keyed to a unique id so multiples can coexist. */
export function LineChart({ data, height = 180, color = '#373DA6', valueFormat = (v) => v, max: maxProp }) {
  const gid = useId().replace(/:/g, '')
  const W = 600, H = height
  const max = maxProp ?? Math.max(1, ...data.map((d) => d.value))
  const min = Math.min(0, ...data.map((d) => d.value))
  const span = max - min || 1
  const pts = data.map((d, i) => [
    (i / Math.max(1, data.length - 1)) * (W - 8) + 4,
    H - 22 - ((d.value - min) / span) * (H - 40),
  ])
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${path} L${pts[pts.length - 1][0].toFixed(1)},${H - 22} L${pts[0][0].toFixed(1)},${H - 22} Z`

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} preserveAspectRatio="none" role="img"
        aria-label={`Trend from ${data[0]?.label} to ${data[data.length - 1]?.label}`}>
        <defs>
          <linearGradient id={`g${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((f) => (
          <line key={f} x1="0" x2={W} y1={22 + f * (H - 44)} y2={22 + f * (H - 44)} stroke="#E4E7EF" strokeWidth="1" />
        ))}
        <path d={area} fill={`url(#g${gid})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          vectorEffect="non-scaling-stroke" />
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2.5" fill="#fff" stroke={color} strokeWidth="1.5" />)}
      </svg>
      <div className="flex mt-1">
        {data.map((d, i) => (
          <span key={i} className="flex-1 text-center text-2xs text-slate-500 truncate">{d.label}</span>
        ))}
      </div>
      <p className="sr-only">{data.map((d) => `${d.label}: ${valueFormat(d.value)}`).join(', ')}</p>
    </div>
  )
}

/** Donut with a centred readout — used for occupancy, the number owners check first. */
export function DonutChart({ segments, size = 150, thickness = 16, centerValue, centerLabel }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1
  const r = (size - thickness) / 2
  const C = 2 * Math.PI * r
  let offset = 0
  return (
    <div className="flex items-center gap-5 flex-wrap">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" role="img" aria-label="Distribution chart">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#F1F5F9" strokeWidth={thickness} />
          {segments.map((s, i) => {
            const len = (s.value / total) * C
            const el = (
              <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke={s.color || PALETTE[i % PALETTE.length]} strokeWidth={thickness}
                strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset} strokeLinecap="butt" />
            )
            offset += len
            return el
          })}
        </svg>
        {centerValue != null && (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-semibold text-slate-900 tnum leading-none">{centerValue}</span>
            {centerLabel && <span className="text-2xs text-slate-500 mt-1">{centerLabel}</span>}
          </div>
        )}
      </div>
      <ul className="space-y-2 min-w-0 flex-1">
        {segments.map((s, i) => (
          <li key={i} className="flex items-center gap-2.5 text-sm">
            <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ backgroundColor: s.color || PALETTE[i % PALETTE.length] }} />
            <span className="text-slate-600 flex-1 truncate">{s.label}</span>
            <span className="font-medium text-slate-900 tnum">{s.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Horizontal bars — better than vertical when labels are long (expense categories). */
export function HBarChart({ data, valueFormat = (v) => v, color = '#373DA6' }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <ul className="space-y-2.5">
      {data.map((d, i) => (
        <li key={i}>
          <div className="flex justify-between text-sm mb-1 gap-3">
            <span className="text-slate-600 truncate">{d.label}</span>
            <span className="font-medium text-slate-900 tnum shrink-0">{valueFormat(d.value)}</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full transition-all duration-700"
              style={{ width: `${(d.value / max) * 100}%`, backgroundColor: d.color || color }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
