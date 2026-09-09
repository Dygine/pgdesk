import { Megaphone, Phone, Mail, Briefcase, MapPin, ShieldCheck, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import {
  Card, CardHeader, Button, StatusBadge, EmptyState, Avatar, InlineAlert, Skeleton,
} from '@/components/ui'
import { inr, dateFmt, relative } from '@/lib/format'

/** Priorities that deserve a badge; Normal is the unremarkable default. */
const LOUD_PRIORITIES = ['HIGH', 'URGENT', 'CRITICAL']

/* ----------------------------------------------------------- announcements */
export function MyAnnouncements() {
  /* The API returns only announcements published to this resident's
     organisation and branch, within their active date window. Nothing is
     filtered here, because nothing unfiltered is sent. */
  const { data, loading, error, reload } = useApi(() => meApi.announcements(), [], { initial: [] })
  const list = data || []

  return (
    <>
      <div className="mb-5">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900">Announcements</h1>
        <p className="text-sm text-slate-500 mt-0.5">Notices from your PG.</p>
      </div>

      <Card>
        {loading && !data?.length ? (
          <div className="p-4 space-y-2">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20" />)}
          </div>
        ) : error ? (
          <div className="p-4">
            <InlineAlert tone="error">
              Could not load announcements. {error.message}{' '}
              <button onClick={reload} className="underline">Retry</button>
            </InlineAlert>
          </div>
        ) : list.length === 0 ? (
          <EmptyState icon={Megaphone} title="Nothing right now"
            message="Notices from your PG will appear here." />
        ) : (
          <div className="divide-y divide-line">
            {list.map((a) => (
              <article key={a.id} className="p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3 mb-1.5">
                  <h2 className="text-sm font-semibold text-slate-900 min-w-0">{a.title}</h2>
                  {LOUD_PRIORITIES.includes(String(a.priority).toUpperCase()) && (
                    <StatusBadge status={a.priority} />
                  )}
                </div>
                <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{a.message}</p>
                <p className="text-2xs text-slate-500 mt-2.5">{relative(a.created_at)}</p>
              </article>
            ))}
          </div>
        )}
      </Card>
    </>
  )
}

/* --------------------------------------------------------------- my profile */
export function MyProfile() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  /* Everything on this page comes from /me/profile, which derives the resident
     from the token. There is no id in the request, so there is nothing an
     attacker could change to read somebody else's record. */
  const { data: me, loading, error, reload } = useApi(() => meApi.profile(), [])

  const signOut = async () => { await logout(); navigate('/login') }

  if (loading && !me) {
    return (
      <>
        <div className="mb-5">
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900">My profile</h1>
        </div>
        <Card className="p-5 space-y-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}
        </Card>
      </>
    )
  }

  if (error) {
    return (
      <Card className="p-5 space-y-3">
        <InlineAlert tone="error">
          Could not load your profile. {error.message}{' '}
          <button onClick={reload} className="underline">Retry</button>
        </InlineAlert>
        <Button variant="danger" icon={LogOut} onClick={signOut}>Sign out</Button>
      </Card>
    )
  }

  const stay = me?.stay || {}
  const emergency = me?.emergency_contact || {}
  const identity = me?.identity || []
  const amenities = stay.room_type
    ? `${stay.has_ac ? 'AC' : 'Non-AC'}${stay.room_type ? ` · ${stay.room_type}` : ''}`
    : '—'

  return (
    <>
      <div className="mb-5">
        <h1 className="text-xl sm:text-2xl font-semibold text-slate-900">My profile</h1>
        <p className="text-sm text-slate-500 mt-0.5">Your details as your PG has them on file.</p>
      </div>

      <Card className="mb-4">
        <div className="p-5 flex flex-col sm:flex-row items-center sm:items-start gap-5">
          <Avatar name={me?.name} size="xl" />
          <div className="flex-1 min-w-0 text-center sm:text-left">
            <div className="flex flex-wrap items-center gap-2 justify-center sm:justify-start">
              <h2 className="text-lg font-semibold text-slate-900">{me?.name}</h2>
              <StatusBadge status={me?.status} dot />
            </div>
            <p className="text-sm text-slate-500 mt-1">
              {[me?.organization, stay.branch].filter(Boolean).join(' · ') || '—'}
            </p>
            <div className="mt-3 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-left">
              {[[Phone, me?.phone], [Mail, me?.email], [Briefcase, me?.occupation],
                [MapPin, [me?.address, me?.city].filter(Boolean).join(', ')]].map(([Icon, v], i) => (
                <p key={i} className="flex items-center gap-2.5 text-sm text-slate-600 min-w-0">
                  <Icon size={15} className="text-slate-400 shrink-0" />
                  <span className="truncate">{v || '—'}</span>
                </p>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Your room" />
          <dl className="divide-y divide-line">
            {[
              ['Branch', stay.branch || '—'],
              ['Building', stay.building || '—'],
              ['Room', stay.room ? `${stay.room}${stay.room_type ? ` · ${stay.room_type}` : ''}` : '—'],
              ['Bed', stay.bed || '—'],
              ['Amenities', amenities],
              ['Joined', stay.joining_date ? dateFmt(stay.joining_date, 'long') : '—'],
              ['Monthly rent', inr(stay.monthly_rent || 0)],
              ['Deposit held', inr(stay.security_deposit || 0)],
              ['Meal plan', stay.meal_plan || '—'],
            ].map(([k, v]) => (
              <div key={k} className="px-5 py-2.5 grid grid-cols-3 gap-3">
                <dt className="text-xs text-slate-500">{k}</dt>
                <dd className="col-span-2 text-sm text-slate-800">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Emergency contact" />
            <div className="p-5">
              {emergency.name ? (
                <>
                  <p className="text-base font-medium text-slate-900">{emergency.name}</p>
                  {emergency.relation && <p className="text-sm text-slate-500">{emergency.relation}</p>}
                  {emergency.phone && (
                    <p className="text-sm text-slate-700 mt-2 flex items-center gap-2">
                      <Phone size={14} className="text-slate-400" />{emergency.phone}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-slate-500">
                  No emergency contact on file. Ask the PG office to add one.
                </p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Identity" />
            {identity.length === 0 ? (
              <div className="p-5">
                <p className="text-sm text-slate-500">No identity document recorded yet.</p>
              </div>
            ) : (
              <div className="divide-y divide-line">
                {identity.map((k, i) => {
                  const verified = String(k.status).toUpperCase() === 'VERIFIED'
                  return (
                    <div key={i} className="p-5 flex items-center gap-3">
                      <span className={`h-10 w-10 rounded-lg inline-flex items-center justify-center shrink-0 ${
                        verified ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                        <ShieldCheck size={19} />
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">{k.id_type}</p>
                        <p className="text-xs text-slate-500">
                          {/* The number itself is deliberately not sent to the portal. */}
                          {verified && k.verified_at
                            ? `Verified ${dateFmt(k.verified_at, 'long')}`
                            : 'Awaiting verification by the PG office'}
                        </p>
                      </div>
                      <StatusBadge status={k.status} className="ml-auto" />
                    </div>
                  )
                })}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="Account" />
            <div className="p-5 space-y-3">
              <InlineAlert tone="info">
                Changes to your personal details are made by the PG office — raise a
                request from the Support page and they will update your record.
              </InlineAlert>
              <Button variant="danger" icon={LogOut} className="w-full" onClick={signOut}>
                Sign out
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
