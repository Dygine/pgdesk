import { Link } from 'react-router-dom'
import {
  Home, BedDouble, IndianRupee, MessageSquareWarning, Megaphone, QrCode, Bell,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, Skeleton, InlineAlert, Button,
} from '@/components/ui'
import { inr, dateFmt, relative } from '@/lib/format'

export default function MyHome() {
  const { data, loading, error } = useApi(() => meApi.home(), [])

  if (error) {
    return (<><PageHeader title="My stay" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My stay" /><Skeleton className="h-64" /></>)
  }

  const { resident, placement, rent } = data

  return (
    <>
      <PageHeader title={`Hello, ${resident.name.split(' ')[0]}`}
        subtitle="Your room, your rent and anything that needs you." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Room" value={placement.room || '—'} icon={Home} tone="brand"
          sub={placement.bed ? `Bed ${placement.bed}` : 'No bed assigned yet'} />
        <StatCard label="Monthly rent" value={inr(resident.monthly_rent)}
          icon={IndianRupee} tone="violet" />
        <StatCard label="Outstanding" value={inr(rent.outstanding)}
          tone={rent.outstanding > 0 ? 'amber' : 'emerald'}
          sub={rent.next_due_date ? `Next due ${dateFmt(rent.next_due_date)}` : 'Nothing due'}
          to="/me/rent" />
        <StatCard label="Open complaints" value={data.open_complaints}
          icon={MessageSquareWarning}
          tone={data.open_complaints ? 'rose' : 'slate'} to="/me/complaints" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Where you live"
            action={<StatusBadge status={resident.status} dot />} />
          <dl className="divide-y divide-line">
            {[['Branch', placement.branch], ['Building', placement.building],
              ['Floor', placement.floor], ['Room', placement.room],
              ['Room type', placement.room_type], ['Bed', placement.bed],
              ['Air conditioned', placement.has_ac == null ? null
                : (placement.has_ac ? 'Yes' : 'No')],
              ['Joined', resident.joining_date ? dateFmt(resident.joining_date) : null],
              ['Deposit held', inr(resident.security_deposit)]].map(([k, v]) => (
              <div key={k} className="px-5 py-2.5 grid grid-cols-3 gap-3">
                <dt className="text-xs text-slate-500">{k}</dt>
                <dd className="col-span-2 text-sm text-slate-800">{v || '—'}</dd>
              </div>
            ))}
          </dl>
          <div className="px-5 py-4 border-t border-line flex gap-2">
            <Link to="/me/scan" className="flex-1">
              <Button icon={QrCode} className="w-full">My gate QR</Button>
            </Link>
            <Link to="/me/rent" className="flex-1">
              <Button variant="primary" className="w-full">View rent</Button>
            </Link>
          </div>
        </Card>

        <Card>
          <CardHeader title="Notices" subtitle={`${data.unread_notifications} unread`}
            action={<Link to="/me/announcements"><Button size="sm">All notices</Button></Link>} />
          {data.announcements.length === 0 ? (
            <EmptyState icon={Megaphone} compact title="Nothing right now"
              message="Announcements from your PG appear here." />
          ) : (
            <div className="divide-y divide-line">
              {data.announcements.map((a) => (
                <div key={a.id} className="px-5 py-3.5">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <p className="text-sm font-medium text-slate-900">{a.title}</p>
                    <StatusBadge status={a.priority}
                      tone={a.priority === 'HIGH' || a.priority === 'URGENT' ? 'rose' : 'slate'} />
                  </div>
                  <p className="text-sm text-slate-600">{a.message}</p>
                  <p className="text-2xs text-slate-400 mt-1">{relative(a.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
