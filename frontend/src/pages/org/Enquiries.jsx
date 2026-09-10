import { useState } from 'react'
import {
  Inbox, Phone, Mail, Calendar, ArrowRight, CheckCircle2, MessageSquare,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useApi } from '@/lib/useApi'
import { enquiryApi } from '@/services/api/enquiryApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, Button, Tabs, StatusBadge, EmptyState, InlineAlert, Skeleton, Modal,
  FormField, Textarea, StatCard,
} from '@/components/ui'
import { dateFmt, dateTimeFmt } from '@/lib/format'

/**
 * Leads from the public listing.
 *
 * These are people, not records, and the screen is built around the one thing
 * staff actually do with them: ring them back. So the phone number is a tap
 * target rather than text, and moving an enquiry along is one button rather
 * than a form.
 *
 * The statuses are a funnel, not a state machine - staff can jump to any of
 * them, because someone who walked in unannounced skips straight to VISITED and
 * a rigid order would just be lied to.
 */
const STATUSES = [
  { value: 'NEW', label: 'New', tone: 'brand' },
  { value: 'CONTACTED', label: 'Contacted', tone: 'blue' },
  { value: 'VISITED', label: 'Visited', tone: 'violet' },
  { value: 'CONVERTED', label: 'Moved in', tone: 'emerald' },
  { value: 'CLOSED', label: 'Closed', tone: 'slate' },
]

const toneFor = (s) => STATUSES.find((x) => x.value === s)?.tone || 'slate'
const labelFor = (s) => STATUSES.find((x) => x.value === s)?.label || s

export default function Enquiries() {
  const navigate = useNavigate()
  const { success, error } = useToast()
  const [tab, setTab] = useState('NEW')
  const [notesFor, setNotesFor] = useState(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)

  const list = useApi(() => enquiryApi.list({
    status: tab === 'all' ? undefined : tab, page_size: 100,
  }), [tab])

  const rows = list.data?.items || []

  const move = async (row, status) => {
    setBusy(true)
    try {
      await enquiryApi.update(row.id, { status })
      success(`Marked ${labelFor(status).toLowerCase()}`)
      list.reload()
    } catch (err) {
      error('Could not update', err.message)
    } finally { setBusy(false) }
  }

  const saveNotes = async () => {
    setBusy(true)
    try {
      await enquiryApi.update(notesFor.id, { staff_notes: notes })
      success('Note saved')
      setNotesFor(null)
      list.reload()
    } catch (err) {
      error('Could not save the note', err.message)
    } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Enquiries"
        subtitle="People who found your PG through the public listing." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Showing" value={rows.length} icon={Inbox} tone="brand" />
        <StatCard label="With a phone number" tone="blue"
          value={rows.filter((r) => r.phone).length} />
        <StatCard label="Email verified" tone="emerald"
          value={rows.filter((r) => r.email_verified).length} />
        <StatCard label="Moved in" tone="violet"
          value={rows.filter((r) => r.status === 'CONVERTED').length} />
      </div>

      <Card>
        <Tabs value={tab} onChange={setTab} tabs={[
          ...STATUSES.map((s) => ({ value: s.value, label: s.label })),
          { value: 'all', label: 'All' },
        ]} />

        {list.error ? (
          <InlineAlert tone="error" className="m-4">{list.error.message}</InlineAlert>
        ) : list.loading && !list.data ? (
          <div className="p-4 space-y-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Inbox} title="Nothing here yet"
            message={tab === 'NEW'
              ? 'New enquiries land here. If none are arriving, check that at least one branch is listed publicly under Branches → Listing.'
              : 'No enquiries with this status.'} />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((e) => (
              <div key={e.id} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-slate-900">{e.full_name}</p>
                      <StatusBadge status={labelFor(e.status)} tone={toneFor(e.status)} dot />
                      {e.email_verified && (
                        <span className="inline-flex items-center gap-1 text-2xs text-emerald-700">
                          <CheckCircle2 size={11} /> verified
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {e.branch_name} · {dateTimeFmt(e.created_at)}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs">
                  {e.phone && (
                    <a href={`tel:${e.phone}`}
                      className="inline-flex items-center gap-1.5 text-brand-700 hover:text-brand-800">
                      <Phone size={12} /> {e.phone}
                    </a>
                  )}
                  <a href={`mailto:${e.email}`}
                    className="inline-flex items-center gap-1.5 text-slate-600 hover:text-slate-900">
                    <Mail size={12} /> {e.email}
                  </a>
                  {e.move_in_date && (
                    <span className="inline-flex items-center gap-1.5 text-slate-500">
                      <Calendar size={12} /> wants {dateFmt(e.move_in_date)}
                    </span>
                  )}
                </div>

                {e.message && (
                  <p className="text-sm text-slate-700 mt-2 rounded-lg bg-slate-50 p-2.5">
                    {e.message}
                  </p>
                )}
                {e.staff_notes && (
                  <p className="text-xs text-slate-500 mt-2">
                    <span className="font-medium">Note:</span> {e.staff_notes}
                  </p>
                )}

                <div className="flex flex-wrap gap-2 mt-3">
                  <PermissionGuard perm="customers.edit">
                    {STATUSES.filter((s) => s.value !== e.status).slice(0, 3).map((s) => (
                      <Button key={s.value} size="sm" disabled={busy}
                        onClick={() => move(e, s.value)}>{s.label}</Button>
                    ))}
                    <Button size="sm" icon={MessageSquare} disabled={busy}
                      onClick={() => { setNotesFor(e); setNotes(e.staff_notes || '') }}>
                      Note
                    </Button>
                  </PermissionGuard>
                  <PermissionGuard perm="customers.checkin">
                    {/* The handover to the real workflow. An enquiry is not a
                        resident - check-in is what assigns a bed, sets rent and
                        raises the first invoice, and duplicating any of that
                        here would create a second way to get it wrong. */}
                    <Button size="sm" variant="primary" iconRight={ArrowRight}
                      onClick={() => navigate('/app/check-in')}>
                      Check in
                    </Button>
                  </PermissionGuard>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={!!notesFor} onClose={() => setNotesFor(null)} size="sm"
        title={`Note — ${notesFor?.full_name || ''}`}
        footer={<><Button onClick={() => setNotesFor(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={saveNotes}>Save note</Button></>}>
        <FormField label="Internal note" hint="Only staff see this.">
          <Textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Called on Tuesday, visiting Saturday morning." />
        </FormField>
      </Modal>
    </>
  )
}
