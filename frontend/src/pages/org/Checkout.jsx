import { useRef, useState } from 'react'
import { LogOut, TriangleAlert, CalendarClock, Check, X, Plus, DoorClosed } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { invoiceApi } from '@/services/api/invoiceApi'
import { noticeApi } from '@/services/api/noticeApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Select, Input, Textarea, InlineAlert,
  StatusBadge, EmptyState, Skeleton, ConfirmDialog, Modal,
} from '@/components/ui'
import { inr, dateFmt, today } from '@/lib/format'

function whenLabel(days) {
  if (days < 0) return { text: `${Math.abs(days)} day${days === -1 ? '' : 's'} past the date`, tone: 'rose' }
  if (days === 0) return { text: 'Leaving today', tone: 'rose' }
  if (days <= 7) return { text: `In ${days} day${days === 1 ? '' : 's'}`, tone: 'amber' }
  return { text: `In ${days} days`, tone: 'slate' }
}

/**
 * Two jobs on one screen. The top half is the notice list: residents who have
 * said they are moving out, with how long is left. The bottom half closes a
 * stay and releases the bed - the same checkout as before, now reachable in one
 * tap from a notice.
 */
export default function Checkout() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const formRef = useRef(null)
  const [residentId, setResidentId] = useState('')
  const [checkoutDate, setCheckoutDate] = useState(today())
  const [notes, setNotes] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [decision, setDecision] = useState(null)      // { notice, kind: 'ack'|'cancel' }
  const [note, setNote] = useState('')
  const [recording, setRecording] = useState(false)
  const [rec, setRec] = useState({})

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId])
  const notices = useApi(() => noticeApi.list({ branch_id: activeBranchId }), [activeBranchId])
  const dues = useApi(
    () => (residentId ? invoiceApi.list({ resident_id: residentId, page_size: 50 })
      : Promise.resolve({ items: [] })),
    [residentId])

  const rows = residents.data?.items || []
  const noticeRows = notices.data || []
  const resident = rows.find((r) => r.id === residentId)
  const noticeFor = noticeRows.find((n) => n.resident_id === residentId)
  const outstanding = (dues.data?.items || [])
    .filter((i) => i.status !== 'CANCELLED')
    .reduce((a, i) => a + Number(i.balance || 0), 0)

  const startCheckout = (n) => {
    setResidentId(n.resident_id)
    setCheckoutDate(n.days_left > 0 ? n.planned_checkout_date : today())
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const submit = async () => {
    setBusy(true)
    try {
      await residentApi.checkout(residentId, {
        checkout_date: checkoutDate || null, notes: notes || null,
      })
      success(`${resident.full_name} checked out`, 'Their bed is available again.')
      setResidentId(''); setNotes(''); setConfirm(false)
      residents.reload(); notices.reload()
    } catch (err) {
      error('Checkout failed', err.message)
    } finally { setBusy(false) }
  }

  const decide = async () => {
    setBusy(true)
    try {
      if (decision.kind === 'ack') {
        await noticeApi.acknowledge(decision.notice.id, { note: note || null })
        success('Notice acknowledged', `${decision.notice.resident} has been told.`)
      } else {
        await noticeApi.cancel(decision.notice.id, { note: note || null })
        success('Notice cancelled', `${decision.notice.resident} stays on as normal.`)
      }
      setDecision(null); setNote('')
      notices.reload(); residents.reload()
    } catch (err) { error('That did not go through', err.message) }
    finally { setBusy(false) }
  }

  const record = async () => {
    if (!rec.resident_id) return error('Choose the resident.')
    if (!rec.date) return error('Choose the day they are leaving.')
    setBusy(true)
    try {
      await noticeApi.record(rec.resident_id, {
        planned_checkout_date: rec.date, reason: rec.reason || null })
      success('Notice recorded', 'The resident can see it in their app.')
      setRecording(false); setRec({})
      notices.reload(); residents.reload()
    } catch (err) { error('Could not record the notice', err.message) }
    finally { setBusy(false) }
  }

  const withoutNotice = rows.filter((r) => !noticeRows.some((n) => n.resident_id === r.id))

  return (
    <>
      <PageHeader title="Checkout"
        subtitle="Who is moving out and when, and closing a stay when they leave."
        actions={<PermissionGuard perm="customers.checkout">
          <Button icon={Plus} onClick={() => { setRec({ date: '' }); setRecording(true) }}>
            Record a notice</Button>
        </PermissionGuard>} />

      <Card className="mb-4">
        <CardHeader title="Moving out"
          subtitle="Residents give notice from their app. Short notice is flagged against the deposit." />
        {notices.loading && !notices.data ? <div className="p-5"><Skeleton className="h-24" /></div>
          : noticeRows.length === 0 ? (
            <EmptyState compact icon={DoorClosed} title="Nobody has given notice"
              message="When a resident says they are moving out, it appears here with the days left." />
          ) : (
            <div className="divide-y divide-line">
              {noticeRows.map((n) => {
                const w = whenLabel(n.days_left)
                return (
                  <div key={n.id} className="px-4 sm:px-5 py-4 flex flex-col md:flex-row md:items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-semibold text-slate-900">{n.resident}</p>
                        <StatusBadge status={w.text} tone={w.tone} dot />
                        {n.short_notice && (
                          <StatusBadge status={`Short notice · ${n.days_given} of ${n.notice_days_required} days`} tone="rose" />
                        )}
                        {n.status === 'SUBMITTED' && <StatusBadge status="New" tone="violet" />}
                      </div>
                      <p className="text-xs text-slate-500 mt-1 tnum">
                        Leaving {dateFmt(n.planned_checkout_date)}
                        {n.room ? ` · Room ${n.room}${n.bed ? `, bed ${n.bed}` : ''}` : ''}
                        {` · told us ${dateFmt(n.notice_date)}`}
                        {n.raised_by === 'staff' ? ' at the desk' : ' in the app'}
                      </p>
                      {n.reason && <p className="text-xs text-slate-600 mt-1">“{n.reason}”</p>}
                      <p className="text-2xs text-slate-500 mt-1 tnum">
                        Deposit held {inr(n.security_deposit || 0)}
                        {n.outstanding > 0.009 ? ` · ${inr(n.outstanding)} unpaid` : ' · nothing unpaid'}
                      </p>
                    </div>
                    <PermissionGuard perm="customers.checkout">
                      <div className="flex gap-2 flex-wrap md:justify-end shrink-0">
                        {n.status === 'SUBMITTED' && (
                          <Button size="sm" icon={Check}
                            onClick={() => { setNote(''); setDecision({ notice: n, kind: 'ack' }) }}>
                            Acknowledge</Button>
                        )}
                        <Button size="sm" variant="primary" icon={LogOut} onClick={() => startCheckout(n)}>
                          Check out</Button>
                        <Button size="sm" variant="ghost" icon={X}
                          onClick={() => { setNote(''); setDecision({ notice: n, kind: 'cancel' }) }}>
                          Cancel notice</Button>
                      </div>
                    </PermissionGuard>
                  </div>
                )
              })}
            </div>
          )}
      </Card>

      <div ref={formRef} className="grid lg:grid-cols-2 gap-4 scroll-mt-20">
        <Card>
          <CardHeader title="Check someone out" subtitle="Closes the stay and frees the bed." />
          {residents.loading ? <div className="p-5"><Skeleton className="h-40" /></div> : (
            <div className="p-5 space-y-4">
              <FormField label="Resident" required>
                <Select value={residentId} onChange={(e) => setResidentId(e.target.value)}>
                  <option value="">Choose a resident…</option>
                  {rows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name}{r.placement?.room ? ` — room ${r.placement.room}` : ''}
                      {r.status === 'NOTICE' ? ' (on notice)' : ''}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Checkout date" required>
                <Input type="date" value={checkoutDate}
                  onChange={(e) => setCheckoutDate(e.target.value)} />
              </FormField>
              <FormField label="Notes" hint="Kept on the resident record.">
                <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Room handed over, deposit refunded by UPI" />
              </FormField>
              <Button variant="danger" icon={LogOut} className="w-full"
                disabled={!residentId || !can('customers.checkout')} onClick={() => setConfirm(true)}>
                Check out
              </Button>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Before you close this stay" />
          <div className="p-5 space-y-4">
            {!resident ? (
              <EmptyState compact title="Choose a resident"
                message="Their bed, their notice and any unpaid invoices appear here." />
            ) : (
              <>
                <div className="rounded-lg border border-line p-4 space-y-2">
                  <p className="text-sm font-medium text-slate-900">{resident.full_name}</p>
                  <p className="text-xs text-slate-500">
                    {resident.placement?.room
                      ? `Room ${resident.placement.room} · bed ${resident.placement.bed_number}`
                      : 'No bed assigned'}
                  </p>
                  <div className="flex items-center gap-2 pt-1">
                    <StatusBadge status={resident.status === 'NOTICE' ? 'Notice Period' : resident.status} dot />
                    <span className="text-xs text-slate-500 tnum">
                      Joined {resident.joining_date ? dateFmt(resident.joining_date) : '—'}
                    </span>
                  </div>
                </div>

                {noticeFor ? (
                  <InlineAlert tone={noticeFor.short_notice ? 'warn' : 'info'} icon={CalendarClock}
                    title={`Gave notice for ${dateFmt(noticeFor.planned_checkout_date)}`}>
                    {noticeFor.days_given} days' notice against {noticeFor.notice_days_required} required
                    {noticeFor.short_notice ? ' - short notice.' : '.'} Checking out closes the notice.
                  </InlineAlert>
                ) : (
                  <InlineAlert tone="info" title="No notice on record">
                    Checkout still works. If they told you in person, record the notice first so
                    the deposit settlement has a date to go by.
                  </InlineAlert>
                )}

                {outstanding > 0.009 ? (
                  <InlineAlert tone="warn" icon={TriangleAlert}
                    title={`${inr(outstanding)} still outstanding`}>
                    Checkout is not blocked, but the unpaid invoices stay open against this
                    resident. Settle or write them off first if that is the intention.
                  </InlineAlert>
                ) : (
                  <InlineAlert tone="success" title="Nothing outstanding">
                    Every invoice for this resident is settled.
                  </InlineAlert>
                )}

                <div className="rounded-lg bg-slate-50 border border-line p-3.5">
                  <p className="text-xs text-slate-600">
                    The bed returns to <span className="font-medium text-emerald-700">available</span>{' '}
                    immediately. The placement history stays on the resident record, so
                    reports still show where they lived.
                  </p>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>

      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} tone="danger"
        title={`Check out ${resident?.full_name}?`} confirmLabel="Check out"
        loading={busy}
        message={outstanding > 0.009
          ? `${inr(outstanding)} is still outstanding. Their bed will be released anyway.`
          : 'Their bed will be released and made available.'}
        onConfirm={submit} />

      <Modal open={!!decision} onClose={() => setDecision(null)} size="sm"
        title={decision?.kind === 'ack' ? 'Acknowledge this notice?' : 'Cancel this notice?'}
        subtitle={decision ? `${decision.notice.resident} · leaving ${dateFmt(decision.notice.planned_checkout_date)}` : ''}
        footer={<><Button onClick={() => setDecision(null)}>Back</Button>
          <Button variant={decision?.kind === 'ack' ? 'primary' : 'danger'} loading={busy} onClick={decide}>
            {decision?.kind === 'ack' ? 'Acknowledge' : 'Cancel notice'}</Button></>}>
        <p className="text-sm text-slate-600 mb-3">
          {decision?.kind === 'ack'
            ? 'The resident is told their leaving date is confirmed.'
            : 'The resident goes back to a normal stay and is told why.'}
        </p>
        <FormField label="Message to the resident" hint="Optional.">
          <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={decision?.kind === 'ack' ? 'Deposit will be settled on the day' : 'Talked it through - staying on'} />
        </FormField>
      </Modal>

      <Modal open={recording} onClose={() => setRecording(false)} size="sm"
        title="Record a notice" subtitle="For a resident who told you in person."
        footer={<><Button onClick={() => setRecording(false)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={record}>Record notice</Button></>}>
        <div className="space-y-4">
          <FormField label="Resident" required>
            <Select value={rec.resident_id || ''} onChange={(e) => setRec({ ...rec, resident_id: e.target.value })}>
              <option value="">Choose…</option>
              {withoutNotice.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}
            </Select>
          </FormField>
          <FormField label="Leaving on" required>
            <Input type="date" min={today()} value={rec.date || ''}
              onChange={(e) => setRec({ ...rec, date: e.target.value })} />
          </FormField>
          <FormField label="Reason">
            <Input value={rec.reason || ''} onChange={(e) => setRec({ ...rec, reason: e.target.value })} />
          </FormField>
        </div>
      </Modal>
    </>
  )
}
