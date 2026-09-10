import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'

const cx = (...a) => a.filter(Boolean).join(' ')

/* ------------------------------------------------------------------ Button */
const BTN = {
  primary: 'bg-brand-700 text-white hover:bg-brand-800 active:bg-brand-900 border-transparent',
  secondary: 'bg-white text-slate-700 hover:bg-slate-50 active:bg-slate-100 border-line',
  ghost: 'bg-transparent text-slate-600 hover:bg-slate-100 border-transparent',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 border-transparent',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700 border-transparent',
  subtle: 'bg-brand-50 text-brand-800 hover:bg-brand-100 border-transparent',
}
const SIZE = {
  sm: 'h-8 px-2.5 text-xs gap-1.5 rounded-md',
  md: 'h-10 px-3.5 text-sm gap-2 rounded-lg',
  lg: 'h-12 px-5 text-[15px] gap-2 rounded-lg',
}

export const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', icon: Icon, iconRight: IconRight, loading, className, children, ...rest }, ref
) {
  return (
    <button ref={ref} {...rest} disabled={rest.disabled || loading}
      className={cx('inline-flex items-center justify-center font-medium border transition-colors select-none',
        'disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap',
        BTN[variant], SIZE[size], className)}>
      {loading ? <Loader2 size={size === 'sm' ? 14 : 16} className="animate-spin" />
        : Icon ? <Icon size={size === 'sm' ? 14 : 16} /> : null}
      {children}
      {IconRight && <IconRight size={size === 'sm' ? 14 : 16} />}
    </button>
  )
})

/* -------------------------------------------------------------- Icon button */
export function IconButton({ icon: Icon, label, className, size = 18, ...rest }) {
  return (
    <button {...rest} aria-label={label} title={label}
      className={cx('inline-flex items-center justify-center rounded-lg text-slate-500',
        'hover:bg-slate-100 hover:text-slate-800 transition-colors h-9 w-9 shrink-0', className)}>
      <Icon size={size} />
    </button>
  )
}

/* -------------------------------------------------------------------- Card */
export function Card({ className, children, ...rest }) {
  return <div {...rest} className={cx('card', className)}>{children}</div>
}
export function CardHeader({ title, subtitle, action, className }) {
  return (
    <div className={cx('flex items-start justify-between gap-3 px-4 sm:px-5 py-3.5 border-b border-line', className)}>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-slate-900 truncate">{title}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
export const CardBody = ({ className, children }) => (
  <div className={cx('p-4 sm:p-5', className)}>{children}</div>
)

/* ------------------------------------------------------------- StatusBadge */
export const TONES = {
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  amber:   'bg-amber-50 text-amber-800 ring-amber-600/20',
  rose:    'bg-rose-50 text-rose-700 ring-rose-600/20',
  blue:    'bg-blue-50 text-blue-700 ring-blue-600/20',
  brand:   'bg-brand-50 text-brand-800 ring-brand-600/20',
  slate:   'bg-slate-100 text-slate-700 ring-slate-500/20',
  violet:  'bg-violet-50 text-violet-700 ring-violet-600/20',
  teal:    'bg-teal-50 text-teal-700 ring-teal-600/20',
}

/** One place decides what colour a status is, everywhere in the product. */
export const STATUS_TONE = {
  Active: 'emerald', Occupied: 'brand', Vacant: 'emerald', Reserved: 'amber',
  'Notice Period': 'amber', Blocked: 'slate', Maintenance: 'rose',
  Paid: 'emerald', Pending: 'amber', Partial: 'blue', Overdue: 'rose', Waived: 'slate',
  Trial: 'blue', 'Expiring soon': 'amber', Expired: 'rose', Suspended: 'rose', Cancelled: 'slate',
  Open: 'rose', Assigned: 'amber', 'In Progress': 'blue', Resolved: 'emerald', Closed: 'slate',
  Requested: 'amber', Approved: 'emerald', Rejected: 'rose', 'Checked In': 'blue', 'Checked Out': 'slate',
  Present: 'emerald', Absent: 'rose', Late: 'amber', Leave: 'blue', Out: 'slate',
  Enquiry: 'violet', Booking: 'blue', Completed: 'emerald', Available: 'emerald', Booked: 'brand',
  Deactivated: 'slate', Archived: 'slate', 'Pending verification': 'amber',
  Low: 'slate', Medium: 'blue', High: 'amber', Urgent: 'rose', Waiting: 'amber',
  Good: 'emerald', Fair: 'amber', 'Needs repair': 'rose', 'In use': 'emerald',
  'In storage': 'slate', 'Under repair': 'amber',
  Answered: 'blue', Working: 'emerald', 'Out of service': 'rose', Retired: 'slate',
  Full: 'rose', 'Filling up': 'amber', Free: 'emerald', 'Low stock': 'rose', 'In stock': 'emerald',
  Inside: 'amber', Left: 'slate', 'Not marked': 'amber', Today: 'brand', Verified: 'emerald',
  Entry: 'emerald', Exit: 'slate', Important: 'amber', Normal: 'slate',
  'All branches': 'brand', 'Counted in': 'emerald', 'Currently out': 'slate',
}

export function StatusBadge({ status, tone, dot = false, className }) {
  const t = tone || STATUS_TONE[status] || 'slate'
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap',
      TONES[t], className)}>
      {dot && <span className={cx('h-1.5 w-1.5 rounded-full', {
        emerald: 'bg-emerald-500', amber: 'bg-amber-500', rose: 'bg-rose-500', blue: 'bg-blue-500',
        brand: 'bg-brand-500', slate: 'bg-slate-400', violet: 'bg-violet-500', teal: 'bg-teal-500',
      }[t])} />}
      {status}
    </span>
  )
}

/* ------------------------------------------------------------------ Avatar */
export function Avatar({ name = '?', color = '#475569', size = 'md', className }) {
  const dims = { xs: 'h-6 w-6 text-[10px]', sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-14 w-14 text-lg', xl: 'h-20 w-20 text-2xl' }[size]
  const ini = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  return (
    <span className={cx('inline-flex items-center justify-center rounded-full font-semibold text-white shrink-0', dims, className)}
      style={{ backgroundColor: color }} aria-hidden="true">{ini}</span>
  )
}

/* --------------------------------------------------------------- Form bits */
export function FormField({ label, required, hint, error, children, className, htmlFor }) {
  return (
    <div className={cx('min-w-0', className)}>
      {label && (
        <label htmlFor={htmlFor} className="block text-[13px] font-medium text-slate-700 mb-1.5">
          {label}{required && <span className="text-rose-500 ml-0.5" aria-hidden="true">*</span>}
        </label>
      )}
      {children}
      {error ? <p className="text-xs text-rose-600 mt-1.5">{error}</p>
        : hint ? <p className="text-xs text-slate-500 mt-1.5">{hint}</p> : null}
    </div>
  )
}

const FIELD = 'w-full rounded-lg border bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 transition-colors disabled:bg-slate-50 disabled:text-slate-500'
export const Input = forwardRef(function Input({ error, className, ...rest }, ref) {
  return <input ref={ref} {...rest}
    className={cx(FIELD, 'h-10', error ? 'border-rose-400' : 'border-line hover:border-slate-300', className)} />
})
export const Select = forwardRef(function Select({ error, className, children, ...rest }, ref) {
  return (
    <select ref={ref} {...rest}
      className={cx(FIELD, 'h-10 pr-8 appearance-none bg-no-repeat', error ? 'border-rose-400' : 'border-line hover:border-slate-300', className)}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3e%3c/svg%3e\")", backgroundPosition: 'right 0.5rem center', backgroundSize: '1.25rem' }}>
      {children}
    </select>
  )
})
export const Textarea = forwardRef(function Textarea({ error, className, ...rest }, ref) {
  return <textarea ref={ref} rows={3} {...rest}
    className={cx(FIELD, 'py-2.5 resize-y', error ? 'border-rose-400' : 'border-line hover:border-slate-300', className)} />
})

export function Checkbox({ label, description, className, ...rest }) {
  return (
    <label className={cx('flex items-start gap-2.5 cursor-pointer select-none group', className)}>
      <input type="checkbox" {...rest}
        className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-700 focus:ring-brand-500 cursor-pointer" />
      <span className="min-w-0">
        <span className="block text-sm text-slate-700 group-hover:text-slate-900">{label}</span>
        {description && <span className="block text-xs text-slate-500">{description}</span>}
      </span>
    </label>
  )
}

/**
 * The on/off switch used everywhere.
 *
 * The knob used to be absolutely positioned with no `left`. Inside a <button>
 * Chrome and the Android WebView centre the content, so the knob started in the
 * middle of the track: "off" sat halfway and "on" hung ~10px past the right
 * edge. Every toggle in the product looked broken. Now the track is a flex row
 * with 2px padding and the knob only ever moves by transform, so its position
 * cannot depend on how a browser lays out button content.
 */
const SWITCH_SIZE = {
  sm: { track: 'h-5 w-9', knob: 'h-4 w-4', on: 'translate-x-4' },
  md: { track: 'h-6 w-11', knob: 'h-5 w-5', on: 'translate-x-5' },
}

export function Switch({ checked, onChange, disabled, ariaLabel, size = 'md', className }) {
  const s = SWITCH_SIZE[size] || SWITCH_SIZE.md
  return (
    <button type="button" role="switch" aria-checked={!!checked} aria-label={ariaLabel}
      disabled={disabled} onClick={() => onChange?.(!checked)}
      className={cx('relative inline-flex shrink-0 items-center rounded-full p-0.5',
        'transition-colors duration-200 ease-out cursor-pointer',
        'focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        s.track, checked ? 'bg-brand-700' : 'bg-slate-300 hover:bg-slate-400/80', className)}>
      <span aria-hidden="true"
        className={cx('pointer-events-none block rounded-full bg-white shadow-sm ring-1 ring-black/5',
          'transition-transform duration-200 ease-out', s.knob,
          checked ? s.on : 'translate-x-0')} />
    </button>
  )
}

export function Toggle({ checked, onChange, label, description, disabled, ariaLabel, size }) {
  // `label` may be a node (a name plus a status chip, say), but aria-label must
  // be a string — passing a node there renders "[object Object]" to a screen
  // reader. Callers using a node label pass `ariaLabel` as well.
  const accessibleName = ariaLabel ?? (typeof label === 'string' ? label : undefined)
  if (!label && !description) {
    return <Switch checked={checked} onChange={onChange} disabled={disabled}
      ariaLabel={accessibleName} size={size} />
  }
  return (
    <div className={cx('flex items-center justify-between gap-4 py-2.5', disabled && 'opacity-80')}>
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-800">{label}</div>
        {description && <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>}
      </div>
      <Switch checked={checked} onChange={onChange} disabled={disabled}
        ariaLabel={accessibleName} size={size} />
    </div>
  )
}

/* ---------------------------------------------------------------- Progress */
export function ProgressBar({ value, max = 100, tone = 'brand', className, showLabel }) {
  const p = max ? Math.min(100, (value / max) * 100) : 0
  const bar = { brand: 'bg-brand-600', emerald: 'bg-emerald-500', amber: 'bg-amber-500', rose: 'bg-rose-500', blue: 'bg-blue-500' }[tone]
  return (
    <div className={className}>
      <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
        <div className={cx('h-full rounded-full transition-all duration-500', bar)} style={{ width: `${p}%` }} />
      </div>
      {showLabel && <p className="text-2xs text-slate-500 mt-1 tnum">{Math.round(p)}%</p>}
    </div>
  )
}

/* -------------------------------------------------------------------- Tabs */
export function Tabs({ tabs, value, onChange, className }) {
  return (
    <div className={cx('border-b border-line overflow-x-auto no-scrollbar', className)}>
      <div className="flex gap-1 min-w-max" role="tablist">
        {tabs.map((t) => (
          <button key={t.value} role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
            className={cx('relative px-3 sm:px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap',
              value === t.value ? 'text-brand-800' : 'text-slate-500 hover:text-slate-800')}>
            {t.label}
            {t.count != null && (
              <span className={cx('ml-1.5 rounded-full px-1.5 py-0.5 text-2xs tnum',
                value === t.value ? 'bg-brand-100 text-brand-800' : 'bg-slate-100 text-slate-600')}>{t.count}</span>
            )}
            {value === t.value && <span className="absolute inset-x-2 sm:inset-x-3 -bottom-px h-0.5 bg-brand-700 rounded-full" />}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- Skeleton */
export const Skeleton = ({ className }) => <div className={cx('animate-pulse rounded bg-slate-200', className)} />
