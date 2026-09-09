import { Inbox, ShieldOff, Search } from 'lucide-react'
import { Button } from './primitives'

const cx = (...a) => a.filter(Boolean).join(' ')

/** An empty screen is an invitation to act, so it always offers the next step. */
export function EmptyState({ icon: Icon = Inbox, title, message, action, className, compact }) {
  return (
    <div className={cx('text-center', compact ? 'py-10 px-4' : 'py-16 px-6', className)}>
      <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400 mb-4">
        <Icon size={22} />
      </span>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {message && <p className="text-sm text-slate-500 mt-1.5 max-w-sm mx-auto leading-relaxed">{message}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  )
}

export const NoResults = ({ term, onClear }) => (
  <EmptyState icon={Search} compact title={`No matches for “${term}”`}
    message="Try a shorter search term, or clear the filters to see everything."
    action={onClear && <Button onClick={onClear}>Clear filters</Button>} />
)

/** Shown when a user reaches a route their role does not include. */
export function AccessDenied({ permission, onBack }) {
  return (
    <div className="flex items-center justify-center min-h-[60vh] px-4">
      <div className="card max-w-md w-full p-8 text-center">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-rose-50 text-rose-600 mb-4">
          <ShieldOff size={22} />
        </span>
        <h2 className="text-lg font-semibold text-slate-900">You don’t have access to this page</h2>
        <p className="text-sm text-slate-500 mt-2 leading-relaxed">
          Your role is missing the permission needed to open it. Ask your PG owner to grant it from
          Settings → Roles.
        </p>
        {permission && (
          <p className="mt-4 inline-block rounded-md bg-slate-100 px-2.5 py-1 text-xs font-mono text-slate-600">
            {Array.isArray(permission) ? permission.join(' or ') : permission}
          </p>
        )}
        {onBack && <div className="mt-6"><Button variant="primary" onClick={onBack}>Back to dashboard</Button></div>}
      </div>
    </div>
  )
}

export function InlineAlert({ tone = 'info', title, children, className, icon: Icon }) {
  const map = {
    info: 'bg-blue-50 border-blue-200 text-blue-900',
    warn: 'bg-amber-50 border-amber-200 text-amber-900',
    error: 'bg-rose-50 border-rose-200 text-rose-900',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-900',
  }[tone]
  return (
    <div className={cx('rounded-lg border px-3.5 py-3 text-sm flex gap-2.5', map, className)} role="note">
      {Icon && <Icon size={17} className="shrink-0 mt-0.5" />}
      <div className="min-w-0">
        {title && <p className="font-semibold mb-0.5">{title}</p>}
        <div className="leading-relaxed opacity-90">{children}</div>
      </div>
    </div>
  )
}
