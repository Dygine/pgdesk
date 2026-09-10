import { Link } from 'react-router-dom'
import { Bed, Wind, ShowerHead, User, Lock, Wrench, Clock } from 'lucide-react'
import { Avatar, StatusBadge } from '@/components/ui'
import { inr, dateFmt, relative } from '@/lib/format'
import { useAuth } from '@/context/AuthContext'
import { AccessDenied } from '@/components/ui'

const cx = (...a) => a.filter(Boolean).join(' ')

/* ------------------------------------------------------------ permissions */
/** Wrap any button/section. Renders nothing when the role lacks the permission. */
export function PermissionGuard({ perm, children, fallback = null }) {
  const { can } = useAuth()
  return can(perm) ? children : fallback
}

/** Wrap a route element. Renders a real 403 page instead of a blank screen. */
export function RouteGuard({ perm, children }) {
  const { can } = useAuth()
  if (!can(perm)) return <AccessDenied permission={perm} onBack={() => window.history.back()} />
  return children
}

/* -------------------------------------------------------------- BedCard */
const BED_STYLE = {
  Vacant:         { ring: 'ring-emerald-200', bg: 'bg-emerald-50', text: 'text-emerald-700', icon: Bed },
  Occupied:       { ring: 'ring-brand-200',   bg: 'bg-brand-50',   text: 'text-brand-800',   icon: User },
  Reserved:       { ring: 'ring-amber-200',   bg: 'bg-amber-50',   text: 'text-amber-800',   icon: Clock },
  'Notice Period':{ ring: 'ring-amber-200',   bg: 'bg-amber-50',   text: 'text-amber-800',   icon: Clock },
  Blocked:        { ring: 'ring-slate-200',   bg: 'bg-slate-100',  text: 'text-slate-600',   icon: Lock },
  Maintenance:    { ring: 'ring-rose-200',    bg: 'bg-rose-50',    text: 'text-rose-700',    icon: Wrench },
}

export function BedCard({ bed, customer, onClick, compact }) {
  const st = BED_STYLE[bed.status] || BED_STYLE.Blocked
  const Icon = st.icon
  return (
    <button onClick={onClick} disabled={!onClick}
      className={cx('w-full text-left rounded-lg ring-1 ring-inset transition-all p-2.5',
        st.ring, st.bg, onClick && 'hover:ring-2 cursor-pointer active:scale-[.99]')}>
      <div className="flex items-center gap-2">
        <span className={cx('h-7 w-7 rounded-md bg-white/70 inline-flex items-center justify-center shrink-0', st.text)}>
          <Icon size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <p className={cx('text-sm font-semibold leading-tight', st.text)}>Bed {bed.label}</p>
          <p className="text-2xs text-slate-500 truncate">
            {customer ? customer.name : bed.status}
          </p>
        </div>
      </div>
      {!compact && customer && (
        <p className="text-2xs text-slate-500 mt-1.5 tnum">{inr(bed.rent)}/mo · since {dateFmt(customer.joiningDate, 'short')}</p>
      )}
    </button>
  )
}

/* ------------------------------------------------------------- RoomCard */
export function RoomCard({ room, beds, onClick, branchName }) {
  const occupied = beds.filter((b) => b.status === 'Occupied' || b.status === 'Notice Period').length
  const total = beds.length
  const full = occupied >= total && total > 0
  const empty = occupied === 0

  return (
    <button onClick={onClick}
      className="card p-3.5 text-left w-full hover:shadow-lift transition-all active:scale-[.99] flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-base font-semibold text-slate-900 leading-tight">Room {room.number}</p>
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            {room.sharing}{branchName ? ` · ${branchName}` : ''}
          </p>
        </div>
        {room.status === 'Maintenance'
          ? <StatusBadge status="Maintenance" />
          : <StatusBadge status={full ? 'Full' : empty ? 'Empty' : `${total - occupied} free`}
              tone={full ? 'brand' : empty ? 'emerald' : 'amber'} />}
      </div>

      <div className="flex gap-1" aria-label={`${occupied} of ${total} beds occupied`}>
        {beds.map((b) => (
          <span key={b.id} title={`Bed ${b.label} · ${b.status}`}
            className={cx('h-1.5 flex-1 rounded-full', {
              Occupied: 'bg-brand-600', 'Notice Period': 'bg-amber-500', Vacant: 'bg-emerald-400',
              Reserved: 'bg-amber-400', Blocked: 'bg-slate-300', Maintenance: 'bg-rose-400',
            }[b.status])} />
        ))}
      </div>

      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500 tnum">{occupied}/{total} beds</span>
        <span className="font-semibold text-slate-900 tnum">{inr(room.rent)}</span>
      </div>

      <div className="flex items-center gap-2.5 text-2xs text-slate-400 pt-0.5 border-t border-line">
        <span className="inline-flex items-center gap-1">
          <Wind size={11} />{room.ac ? 'AC' : 'Non-AC'}
        </span>
        {room.attachedBath && <span className="inline-flex items-center gap-1"><ShowerHead size={11} />Attached</span>}
        <span className="ml-auto">{room.type}</span>
      </div>
    </button>
  )
}

/* ----------------------------------------------------------- TenantCard */
export function TenantCard({ customer, room, branch, to, onClick, trailing }) {
  const Wrapper = to ? Link : onClick ? 'button' : 'div'
  return (
    <Wrapper {...(to ? { to } : onClick ? { onClick, type: 'button' } : {})}
      className={cx('flex items-center gap-3 w-full text-left min-w-0',
        (to || onClick) && 'hover:bg-slate-50 rounded-lg -mx-1.5 px-1.5 py-1 transition-colors')}>
      <Avatar name={customer.name} color={customer.avatarColor} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-900 truncate">{customer.name}</p>
        <p className="text-xs text-slate-500 truncate">
          {room ? `Room ${room.number} · Bed ${customer.bedLabel || ''}` : customer.status}
          {branch ? ` · ${branch.name}` : ''}
        </p>
      </div>
      {trailing}
    </Wrapper>
  )
}

/* ------------------------------------------------------ ActivityTimeline */
export function ActivityTimeline({ items, empty }) {
  if (!items.length) return empty || <p className="text-sm text-slate-500 py-6 text-center">No activity yet.</p>
  return (
    <ol className="relative space-y-4">
      <span className="absolute left-[7px] top-2 bottom-2 w-px bg-line" aria-hidden="true" />
      {items.map((it, i) => (
        <li key={it.id || i} className="relative pl-6">
          <span className={cx('absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-white',
            it.tone === 'rose' ? 'bg-rose-400' : it.tone === 'emerald' ? 'bg-emerald-400'
              : it.tone === 'amber' ? 'bg-amber-400' : 'bg-brand-400')} />
          <p className="text-sm text-slate-800 leading-snug">{it.text}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {it.who && <span className="text-slate-500">{it.who} · </span>}
            {relative(it.at)}
          </p>
        </li>
      ))}
    </ol>
  )
}

/* ------------------------------------------------------------ PageHeader */
export function PageHeader({ title, subtitle, actions, breadcrumb, children, className }) {
  return (
    <div className={cx('mb-5', className)}>
      {breadcrumb && <div className="mb-1.5 text-xs text-slate-500 flex items-center gap-1.5 flex-wrap">{breadcrumb}</div>}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 tracking-[-0.01em]">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500 mt-1 leading-relaxed">{subtitle}</p>}
        </div>
        {actions && <div className="flex gap-2 shrink-0 flex-wrap">{actions}</div>}
      </div>
      {children}
    </div>
  )
}

export { UpdateBanner } from './UpdateBanner'
export { ResidentDocuments, DocumentCapture } from './ResidentDocuments'
export {
  PermissionOnboarding, shouldAskPermissions, resetPermissionOnboarding,
} from './PermissionOnboarding'
export { PortalCredentials } from './PortalCredentials'
