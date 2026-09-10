import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation, useNavigate, Link } from 'react-router-dom'
import {
  Menu, X, Bell, ChevronDown, LogOut, User, Lock, ShieldAlert, Check,
  Building2, MoreHorizontal, Sparkles,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import {
  PermissionOnboarding, UpdateBanner, shouldAskPermissions,
} from '@/components/domain'
import { filterNav } from '@/nav/navConfig'
import { Avatar, StatusBadge, Button, InlineAlert, Modal, FormField, Input } from '@/components/ui'
import { GlobalSearch } from './GlobalSearch'
import { useToast } from '@/context/ToastContext'
import { authApi } from '@/services/api/authApi'
import { notificationApi } from '@/services/api/notificationApi'
import { relative } from '@/lib/format'

const cx = (...a) => a.filter(Boolean).join(' ')

/* ------------------------------------------------------------------ brand */
function Brand({ compact }) {
  // The PG's own name, not ours. The org is already in the auth context - the
  // sidebar footer has been showing it all along - so this is a relabel, not a
  // new lookup.
  //
  // Master admins keep "PGDesk": that portal is the platform, not a tenant, and
  // borrowing a customer's name there would be confusing rather than friendly.
  const { org, role } = useAuth() || {}
  const isMaster = role === 'master' || !org?.name
  const title = isMaster ? 'PGDesk' : org.name
  const subtitle = isMaster ? 'PG & hostel operations' : 'Powered by PGDesk'
  const initial = (title || 'P').trim().charAt(0).toUpperCase()

  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <span className="h-8 w-8 rounded-lg bg-brand-800 text-white inline-flex items-center justify-center shrink-0 font-bold text-sm">
        {initial}
      </span>
      {!compact && (
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-white leading-tight truncate">
            {title}
          </span>
          <span className="block text-2xs text-brand-300 leading-tight">{subtitle}</span>
        </span>
      )}
    </div>
  )
}

/* ------------------------------------------------------------- nav list */
function NavList({ groups, onNavigate }) {
  return (
    <nav className="px-3 py-3 space-y-5">
      {groups.map((g) => (
        <div key={g.group}>
          <p className="px-2.5 mb-1.5 text-2xs font-semibold text-brand-400 tracking-wide">{g.group}</p>
          <ul className="space-y-0.5">
            {g.items.map((it) => (
              <li key={it.to}>
                <NavLink to={it.to} end={it.end} onClick={onNavigate}
                  className={({ isActive }) => cx(
                    'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                    isActive ? 'bg-brand-700/70 text-white font-medium' : 'text-brand-200 hover:bg-brand-800/60 hover:text-white'
                  )}>
                  <it.icon size={17} className="shrink-0" />
                  <span className="truncate">{it.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

/* ----------------------------------------------------------- branch switch */
function BranchSelector({ compact }) {
  const { branches, branchScope, setBranchScope, user } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  if (!branches.length) return null

  const label = branchScope === 'all'
    ? (user?.allBranches ? 'All branches' : 'All my branches')
    : branches.find((b) => b.code === branchScope)?.name || 'All branches'

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} aria-haspopup="listbox" aria-expanded={open}
        className="h-9 inline-flex items-center gap-2 rounded-lg border border-line bg-white px-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors max-w-[11rem]">
        <Building2 size={15} className="text-slate-400 shrink-0" />
        <span className="truncate font-medium">{compact ? label.split(' ')[0] : label}</span>
        <ChevronDown size={14} className="text-slate-400 shrink-0" />
      </button>
      {open && (
        <div role="listbox" className="absolute right-0 top-full mt-1.5 w-56 card shadow-pop py-1 z-50 animate-popIn">
          <button onClick={() => { setBranchScope('all'); setOpen(false) }}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 text-left">
            <span>{user?.allBranches ? 'All branches' : 'All my branches'}</span>
            {branchScope === 'all' && <Check size={15} className="text-brand-700" />}
          </button>
          <div className="my-1 border-t border-line" />
          {branches.map((b) => (
            <button key={b.id} onClick={() => { setBranchScope(b.code); setOpen(false) }}
              className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 text-left">
              <span className="truncate">{b.name}</span>
              {branchScope === b.code && <Check size={15} className="text-brand-700 shrink-0" />}
            </button>
          ))}
          {!user?.allBranches && (
            <p className="px-3 py-2 text-2xs text-slate-400 border-t border-line mt-1">
              You can only see branches assigned to your role.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------- notification bell */
/** How often the bell re-checks for new notifications while the app is open. */
const NOTIFICATION_POLL_MS = 60_000

/**
 * Where a notification should take you. Most producers set `link`; the ones
 * addressed by permission ("payment to verify", "checkout notice") carry only
 * an entity type, so the list page for that type is the destination.
 */
const ENTITY_ROUTES = {
  org: {
    payment: '/app/payments', invoice: '/app/invoices', checkout_notice: '/app/checkout',
    query: '/app/queries', complaint: '/app/complaints', visitor: '/app/visitors',
    gate_pass: '/app/gate-passes', customer: '/app/residents', enquiry: '/app/enquiries',
  },
  customer: {
    payment: '/me/rent', invoice: '/me/rent', checkout_notice: '/me/moving-out',
    query: '/me/queries', complaint: '/me/complaints', visitor: '/me/visitors',
    gate_pass: '/me/gate-pass',
  },
}
const linkFor = (n, portal) => {
  const routes = ENTITY_ROUTES[portal] || {}
  const prefix = portal === 'customer' ? '/me' : portal === 'org' ? '/app' : null
  if (n.link && (!prefix || n.link.startsWith(prefix))) return n.link
  return routes[n.entity_type] || null
}

/**
 * The panel is rendered into <body> and placed from the bell's own position.
 *
 * It used to be `absolute right-0` inside the topbar, 22rem wide. On a phone the
 * bell is not at the screen edge - the avatar sits to its right - so a panel
 * that wide, anchored to the bell, ran off the side of the screen in the app.
 * On a phone it is now a sheet with an 8px margin on both sides; from `sm` up it
 * is a 22rem dropdown whose right edge lines up with the bell.
 */
function NotificationBell() {
  const { portal } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const buttonRef = useRef(null)
  const panelRef = useRef(null)

  const place = useCallback(() => {
    const r = buttonRef.current?.getBoundingClientRect()
    if (!r) return
    const vw = window.innerWidth
    setPos(vw < 640
      ? { top: r.bottom + 8, left: 8, right: 8 }
      : { top: r.bottom + 6, right: Math.max(8, vw - r.right), width: Math.min(352, vw - 16) })
  }, [])

  useEffect(() => {
    if (!open) return undefined
    place()
    const outside = (e) => {
      if (buttonRef.current?.contains(e.target) || panelRef.current?.contains(e.target)) return
      setOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', outside)
    document.addEventListener('touchstart', outside, { passive: true })
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('mousedown', outside)
      document.removeEventListener('touchstart', outside)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  /**
   * The API scopes notifications to the authenticated caller - staff see their
   * own, residents see theirs, and the organisation filter is applied server
   * side. There is no scope parameter to pass and nothing to filter here.
   */
  const load = useCallback(async () => {
    try {
      const res = await notificationApi.list({ page_size: 12 })
      setItems(res?.data || [])
      setUnread(res?.unread_count ?? (res?.data || []).filter((n) => !n.read).length)
      setFailed(false)
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, NOTIFICATION_POLL_MS)
    const onResume = () => load()
    window.addEventListener('pgdesk:resume', onResume)
    return () => { clearInterval(timer); window.removeEventListener('pgdesk:resume', onResume) }
  }, [load])

  // Reading one is optimistic: the badge should drop the instant it is clicked,
  // and a failed mark-read is corrected by the next poll rather than by an
  // error message about something the user did not ask to do.
  const openOne = async (n) => {
    const to = linkFor(n, portal)
    if (!n.read) {
      setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read: true } : x)))
      setUnread((u) => Math.max(0, u - 1))
      notificationApi.markRead(n.id).catch(() => load())
    }
    if (to) { setOpen(false); navigate(to) }
  }

  const readAll = async () => {
    setItems((xs) => xs.map((x) => ({ ...x, read: true })))
    setUnread(0)
    try { await notificationApi.markAllRead() } catch { load() }
  }

  const panel = open && pos && createPortal(
    <div ref={panelRef} role="dialog" aria-label="Notifications"
      style={{ top: pos.top, left: pos.left, right: pos.right, width: pos.width }}
      className="fixed z-[60] card shadow-pop animate-popIn overflow-hidden flex flex-col max-h-[min(32rem,calc(100dvh-6rem))]">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-line shrink-0">
        <p className="text-sm font-semibold text-slate-900">Notifications</p>
        <div className="flex items-center gap-3">
          {unread > 0 && (
            <button onClick={readAll} className="text-xs text-brand-700 hover:underline">
              Mark all read
            </button>
          )}
          <button onClick={() => setOpen(false)} aria-label="Close notifications"
            className="sm:hidden text-slate-400 hover:text-slate-700 p-0.5"><X size={16} /></button>
        </div>
      </div>
      <div className="overflow-y-auto overscroll-contain">
        {loading ? (
          <p className="px-4 py-8 text-sm text-slate-500 text-center">Loading…</p>
        ) : failed ? (
          <p className="px-4 py-8 text-sm text-slate-500 text-center">
            Could not load notifications.{' '}
            <button onClick={load} className="text-brand-700 hover:underline">Retry</button>
          </p>
        ) : items.length === 0 ? (
          <p className="px-4 py-8 text-sm text-slate-500 text-center">You&rsquo;re all caught up.</p>
        ) : items.map((n) => (
          <button key={n.id} onClick={() => openOne(n)}
            className={cx('w-full text-left px-4 py-3 border-b border-line last:border-0 hover:bg-slate-50 flex gap-3',
              !n.read && 'bg-brand-50/40')}>
            <span className={cx('mt-1.5 h-2 w-2 rounded-full shrink-0', n.read ? 'bg-transparent' : 'bg-brand-600')} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium text-slate-900 break-words">{n.title}</span>
              <span className="block text-xs text-slate-500 mt-0.5 leading-relaxed break-words">{n.message}</span>
              <span className="block text-2xs text-slate-400 mt-1">{relative(n.created_at)}</span>
            </span>
          </button>
        ))}
      </div>
    </div>,
    document.body,
  )

  return (
    <div className="relative">
      <button ref={buttonRef} onClick={() => setOpen((v) => !v)} aria-expanded={open}
        aria-label={`Notifications, ${unread} unread`}
        className="relative h-9 w-9 inline-flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 transition-colors">
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-rose-500 text-white text-[10px] font-semibold inline-flex items-center justify-center tnum">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {panel}
    </div>
  )
}

/* --------------------------------------------------------------- profile */
function ProfileMenu() {
  const { user, customer, role, org, logout, isMaster, mustChangePassword } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const ref = useRef(null)

  // An account created with a temporary password is asked to change it up front.
  useEffect(() => { if (mustChangePassword) setPwOpen(true) }, [mustChangePassword])
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const me = user || customer
  if (!me) return null

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} aria-haspopup="menu" aria-expanded={open}
        className="flex items-center gap-2 rounded-lg p-1 hover:bg-slate-100 transition-colors">
        <Avatar name={me.name} color={me.avatarColor} size="sm" />
        <span className="hidden lg:block text-left min-w-0 max-w-[9rem]">
          <span className="block text-sm font-medium text-slate-900 truncate leading-tight">{me.name}</span>
          <span className="block text-2xs text-slate-500 truncate">{role?.name}</span>
        </span>
        <ChevronDown size={14} className="text-slate-400 hidden lg:block" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full mt-1.5 w-64 card shadow-pop py-1 z-50 animate-popIn">
          <div className="px-3.5 py-3 border-b border-line">
            <p className="text-sm font-semibold text-slate-900">{me.name}</p>
            <p className="text-xs text-slate-500 truncate">{me.email}</p>
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              <StatusBadge status={role?.name || 'User'} tone="brand" />
              {org && <span className="text-2xs text-slate-500 truncate">{org.name}</span>}
              {isMaster && <StatusBadge status="Platform" tone="violet" />}
            </div>
          </div>
          {[
            { icon: User, label: 'My profile', onClick: () => navigate(customer ? '/me/profile' : '/app/settings') },
            { icon: Lock, label: 'Change password', onClick: () => setPwOpen(true) },
            { icon: ShieldAlert, label: 'Security', onClick: () => navigate(customer ? '/me/profile' : '/app/settings') },
          ].map((it) => (
            <button key={it.label} role="menuitem" onClick={() => { it.onClick(); setOpen(false) }}
              className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-slate-700 hover:bg-slate-50 text-left">
              <it.icon size={16} className="text-slate-400" />{it.label}
            </button>
          ))}
          <div className="border-t border-line my-1" />
          <button role="menuitem" onClick={async () => { await logout(); navigate('/login') }}
            className="w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-rose-600 hover:bg-rose-50 text-left">
            <LogOut size={16} />Sign out
          </button>
        </div>
      )}
      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)}
        forced={mustChangePassword} />
    </div>
  )
}

/**
 * Calls POST /api/v1/auth/change-password. The server revokes every other
 * session on success, so this is also the "someone else may know my password"
 * button.
 */
function ChangePasswordModal({ open, onClose, forced }) {
  const { success, error } = useToast()
  const { replaceAccount } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  // `forced` is the first sign-in on a temporary password - including a
  // resident who scanned a sign-in QR and never saw that password. The server
  // accepts no current password in exactly that state, so none is asked for.
  const submit = async () => {
    if (!forced && !current) return error('Enter your current password.')
    if (next.length < 8) return error('Use at least 8 characters.')
    if (next !== confirm) return error('The two new passwords do not match.')
    setBusy(true)
    try {
      const user = await authApi.changePassword(forced ? null : current, next)
      success(forced ? 'Password set' : 'Password changed',
        forced ? 'Use it with your email next time you sign in.'
          : 'Your other devices have been signed out.')
      setCurrent(''); setNext(''); setConfirm('')
      if (user) replaceAccount(user)
      onClose()
    } catch (err) {
      error(forced ? 'Could not set your password' : 'Could not change your password', err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={forced ? () => {} : onClose} size="sm"
      title={forced ? 'Set your password' : 'Change your password'}
      subtitle={forced ? 'Choose a password you will remember. You sign in with it and your email from now on.' : undefined}
      footer={<>
        {!forced && <Button onClick={onClose}>Cancel</Button>}
        <Button variant="primary" onClick={submit} loading={busy}>
          {forced ? 'Set password' : 'Change password'}
        </Button>
      </>}>
      <div className="space-y-4">
        {!forced && (
          <FormField label="Current password" required>
            <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password" />
          </FormField>
        )}
        <FormField label="New password" required hint="At least 8 characters.">
          <Input type="password" value={next} onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password" />
        </FormField>
        <FormField label="Confirm new password" required>
          <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password" onKeyDown={(e) => e.key === 'Enter' && submit()} />
        </FormField>
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------------ bottom nav */
function isActivePath(pathname, item) {
  if (item.end) return pathname === item.to || pathname === `${item.to}/`
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}

/**
 * The phone tab bar. The current tab gets a filled pill in the brand colour,
 * a heavier icon and a bold label - the old grey-to-navy text change was too
 * faint to see at a glance on a phone. "More" lights up while the drawer is
 * open, and whenever the current page is not one of the tabs, so there is
 * always exactly one answer to "where am I".
 */
function BottomNav({ items, onMore, drawerOpen }) {
  const { pathname } = useLocation()
  const anyActive = items.some((it) => isActivePath(pathname, it))
  const moreActive = drawerOpen || !anyActive
  const tab = 'relative w-full flex flex-col items-center gap-1 pt-2 pb-1.5 text-[11px] leading-none select-none transition active:scale-95'
  const pill = 'h-8 w-14 rounded-full inline-flex items-center justify-center transition-colors duration-200'
  const noTapFlash = { WebkitTapHighlightColor: 'transparent' }

  return (
    <nav data-bottom-nav aria-label="Primary"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-line safe-b shadow-[0_-2px_10px_rgba(16,24,40,0.05)]">
      <ul className="flex px-1">
        {items.map((it) => {
          const active = isActivePath(pathname, it)
          return (
            <li key={it.to} className="flex-1 min-w-0">
              <Link to={it.to} aria-current={active ? 'page' : undefined} style={noTapFlash}
                className={cx(tab, active ? 'text-brand-700 font-semibold' : 'text-slate-500')}>
                {it.primary ? (
                  <span className={cx('h-11 w-11 -mt-5 rounded-full inline-flex items-center justify-center text-white shadow-lift ring-4 ring-white transition-colors',
                    active ? 'bg-brand-600' : 'bg-brand-800')}>
                    <it.icon size={20} />
                  </span>
                ) : (
                  <span className={cx(pill, active ? 'bg-brand-100 text-brand-700' : 'active:bg-slate-100')}>
                    <it.icon size={20} strokeWidth={active ? 2.4 : 2} />
                  </span>
                )}
                <span className="max-w-full truncate px-0.5">{it.label}</span>
              </Link>
            </li>
          )
        })}
        <li className="flex-1 min-w-0">
          <button type="button" onClick={onMore} aria-expanded={!!drawerOpen} style={noTapFlash}
            className={cx(tab, moreActive ? 'text-brand-700 font-semibold' : 'text-slate-500')}>
            <span className={cx(pill, moreActive ? 'bg-brand-100 text-brand-700' : 'active:bg-slate-100')}>
              <MoreHorizontal size={20} strokeWidth={moreActive ? 2.4 : 2} />
            </span>
            <span>More</span>
          </button>
        </li>
      </ul>
    </nav>
  )
}

/* ----------------------------------------------------------------- shell */
/**
 * The single layout for every portal at every screen size.
 *  >= lg : fixed sidebar + topbar + content
 *  <  lg : topbar + slide-in drawer (same NavList) + bottom bar
 */
export function AppShell({ navGroups, bottomItems, children, banner, showBranchSelector = true, showSearch = true }) {
  const { can, org, subscription } = useAuth()

  // Asked once, after the first sign-in rather than at launch: a permission
  // prompt on a screen someone has not chosen to trust yet is the one most
  // likely to be refused.
  const [askPermissions, setAskPermissions] = useState(false)
  useEffect(() => {
    let cancelled = false
    shouldAskPermissions().then((yes) => { if (!cancelled) setAskPermissions(yes) })
    return () => { cancelled = true }
  }, [])
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()

  useEffect(() => { setDrawer(false) }, [location.pathname])
  useEffect(() => {
    document.body.style.overflow = drawer ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [drawer])

  const groups = filterNav(navGroups, can)
  const bottom = (bottomItems || []).filter((i) => !i.perm || can(i.perm))

  return (
    <div className="min-h-screen bg-canvas">
      {/* Both live above the layout on purpose. The update gate has to be able
          to cover a screen whose API calls are already failing, and the
          permission flow has to run before anyone reaches a scanner that would
          silently do nothing without it. */}
      <UpdateBanner />
      {askPermissions && (
        <PermissionOnboarding onDone={() => setAskPermissions(false)} />
      )}

      {/* Desktop sidebar */}
      {/* z-40, above the topbar. The topbar uses lg:pl-[16.5rem] (padding, not
          margin), so its box spans the full viewport width and its background
          paints across this column. At equal z-index the topbar wins on DOM
          order and covers the brand block. */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[16.5rem] bg-brand-900 flex-col z-40">
        <div className="h-14 flex items-center px-4 border-b border-brand-800/70 shrink-0"><Brand /></div>
        <div className="flex-1 overflow-y-auto">
          <NavList groups={groups} />
        </div>
        {org && (
          <div className="p-3 border-t border-brand-800/70 shrink-0">
            <div className="rounded-lg bg-brand-800/60 p-3">
              <p className="text-xs font-medium text-white truncate">{org.name}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <StatusBadge status={subscription?.label} tone={subscription?.tone} />
                {subscription?.days > 0 && (
                  <span className="text-2xs text-brand-300 tnum">{subscription.days}d left</span>
                )}
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* Mobile drawer — same NavList component */}
      {drawer && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-slate-900/50 animate-fadeIn" onClick={() => setDrawer(false)} />
          <div className="relative w-[17rem] max-w-[85vw] bg-brand-900 flex flex-col animate-slideLeft">
            <div className="h-14 flex items-center justify-between px-4 border-b border-brand-800/70 shrink-0 safe-t">
              <Brand />
              <button onClick={() => setDrawer(false)} aria-label="Close menu" className="text-brand-300 p-1">
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto"><NavList groups={groups} onNavigate={() => setDrawer(false)} /></div>
          </div>
        </div>
      )}

      {/* Topbar */}
      <header className="lg:pl-[16.5rem] sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-line safe-t">
        <div className="h-14 flex items-center gap-2 sm:gap-3 px-3 sm:px-5">
          <button onClick={() => setDrawer(true)} aria-label="Open menu"
            className="lg:hidden h-9 w-9 inline-flex items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 shrink-0">
            <Menu size={20} />
          </button>
          <Link to="/" className="lg:hidden flex items-center gap-2 mr-auto min-w-0">
            <span className="h-7 w-7 rounded-md bg-brand-800 text-white inline-flex items-center justify-center font-bold text-xs shrink-0">
              {(org?.name || 'P').trim().charAt(0).toUpperCase()}
            </span>
            <span className="text-sm font-semibold text-slate-900 truncate">
              {org?.name || 'PGDesk'}
            </span>
          </Link>
          {showSearch && <div className="hidden md:flex flex-1 min-w-0"><GlobalSearch /></div>}
          <div className="flex items-center gap-1.5 sm:gap-2 ml-auto shrink-0">
            {showBranchSelector && <div className="hidden sm:block"><BranchSelector /></div>}
            <NotificationBell />
            <ProfileMenu />
          </div>
        </div>
        {showSearch && (
          <div className="md:hidden px-3 pb-2.5 flex gap-2">
            <GlobalSearch compact />
            {showBranchSelector && <div className="sm:hidden"><BranchSelector compact /></div>}
          </div>
        )}
      </header>

      {banner}

      <main className="lg:pl-[16.5rem] pb-20 lg:pb-0">
        <div className="px-3 sm:px-5 lg:px-7 py-5 lg:py-7 max-w-[100rem] mx-auto">{children}</div>
      </main>

      {bottom.length > 0 && <BottomNav items={bottom} onMore={() => setDrawer(true)} drawerOpen={drawer} />}
    </div>
  )
}

/** Full-width banner shown when a tenant's subscription has lapsed. */
export function SubscriptionBanner() {
  const { subscription, org, isMaster } = useAuth()
  if (isMaster || !org || !subscription) return null
  if (!['Expired', 'Suspended', 'Expiring soon'].includes(subscription.label)) return null
  const blocked = subscription.label !== 'Expiring soon'
  return (
    <div className="lg:pl-[16.5rem]">
      <div className="px-3 sm:px-5 lg:px-7 pt-4 max-w-[100rem] mx-auto">
        <InlineAlert tone={blocked ? 'error' : 'warn'} icon={ShieldAlert}
          title={blocked ? `Subscription ${subscription.label.toLowerCase()}` : `Subscription expires in ${subscription.days} days`}>
          {blocked
            ? 'Creating and editing records is switched off. Contact the platform administrator to restore access.'
            : 'Renew before the end date to avoid interruption. Contact the platform administrator to extend.'}
        </InlineAlert>
      </div>
    </div>
  )
}
