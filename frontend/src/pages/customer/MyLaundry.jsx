import { useState } from 'react'
import { Shirt, Calendar, X } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, EmptyState, Skeleton, InlineAlert,
  Modal, FormField, Input, StatCard, ProgressBar,
} from '@/components/ui'
import { num, dateFmt, timeOnly } from '@/lib/format'

const TONE = { BOOKED: 'brand', RECEIVED: 'amber', PROCESSING: 'amber',
  READY: 'emerald', COLLECTED: 'slate', CANCELLED: 'slate' }

export default function MyLaundry() {
  const { success, error } = useToast()
  const { data, loading, error: failed, reload } = useApi(() => meApi.laundry(), [])
  const [slot, setSlot] = useState(null)
  const [items, setItems] = useState('5')
  const [busy, setBusy] = useState(false)

  const book = async () => {
    setBusy(true)
    try {
      await meApi.bookLaundry({ slot_id: slot.id, item_count: Number(items) || 1 })
      success('Slot booked', `${dateFmt(slot.on_date)} at ${timeOnly(slot.start_time)}.`)
      setSlot(null)
      reload()
    } catch (err) { error('Could not book that slot', err.message) }
    finally { setBusy(false) }
  }

  const cancel = async (r) => {
    try {
      await meApi.cancelLaundry(r.id)
      success('Booking cancelled')
      reload()
    } catch (err) { error('Could not cancel', err.message) }
  }

  if (failed) {
    return (<><PageHeader title="Laundry" />
      <InlineAlert tone="error" title="Could not load">{failed.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="Laundry" /><Skeleton className="h-64" /></>)
  }

  const slots = data.slots || []
  const requests = data.requests || []
  const active = requests.filter(
    (r) => !['COLLECTED', 'CANCELLED'].includes(r.status))

  return (
    <>
      <PageHeader title="Laundry"
        subtitle="Book a slot, then drop your clothes off during that window." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Active bookings" value={num(active.length)} icon={Shirt} tone="brand" />
        <StatCard label="Ready to collect"
          value={num(requests.filter((r) => r.status === 'READY').length)} tone="emerald" />
        <StatCard label="Slots this fortnight" value={num(slots.length)}
          icon={Calendar} tone="slate" />
        <StatCard label="Free places"
          value={num(slots.reduce((a, s) => a + s.remaining, 0))} tone="violet" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Available slots" subtitle="Next two weeks" />
          {slots.length === 0 ? (
            <EmptyState icon={Calendar} compact title="No slots published"
              message="The laundry team publishes slots a week or two ahead." />
          ) : (
            <div className="p-4 grid sm:grid-cols-2 gap-2.5 max-h-[520px] overflow-y-auto">
              {slots.map((s) => {
                const full = s.remaining <= 0
                return (
                  <button key={s.id} disabled={full || s.mine || s.status === 'CLOSED'}
                    onClick={() => { setSlot(s); setItems('5') }}
                    className={`rounded-lg border p-3.5 text-left transition-colors ${
                      s.mine ? 'border-brand-300 bg-brand-50'
                        : full ? 'border-line bg-slate-50 opacity-60 cursor-not-allowed'
                          : 'border-line hover:bg-slate-50'}`}>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <p className="text-sm font-medium text-slate-900 tnum">
                        {dateFmt(s.on_date)}
                      </p>
                      {s.mine ? <StatusBadge status="Booked" tone="brand" />
                        : full ? <StatusBadge status="Full" tone="slate" /> : null}
                    </div>
                    <p className="text-xs text-slate-600 tnum">
                      {timeOnly(s.start_time)} – {timeOnly(s.end_time)}
                    </p>
                    <div className="mt-2">
                      <ProgressBar value={s.booked} max={s.capacity}
                        tone={full ? 'rose' : 'brand'} />
                      <p className="text-2xs text-slate-500 tnum mt-1">
                        {s.booked}/{s.capacity} taken
                      </p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="My bookings" />
          {requests.length === 0 ? (
            <EmptyState icon={Shirt} compact title="Nothing booked"
              message="Pick a slot to get started." />
          ) : (
            <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
              {requests.map((r) => (
                <div key={r.id} className="px-5 py-3.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-900 tnum">
                      {r.on_date ? dateFmt(r.on_date) : '—'}
                      {r.start_time ? ` · ${timeOnly(r.start_time)}` : ''}
                    </p>
                    <p className="text-2xs text-slate-500">{r.item_count} items</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <StatusBadge status={r.status} tone={TONE[r.status]} dot />
                    {['BOOKED', 'RECEIVED'].includes(r.status) && (
                      <Button size="sm" icon={X} onClick={() => cancel(r)}>Cancel</Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal open={!!slot} onClose={() => setSlot(null)} size="sm" title="Book this slot"
        subtitle={slot ? `${dateFmt(slot.on_date)} · ${timeOnly(slot.start_time)}–${timeOnly(slot.end_time)}` : ''}
        footer={<><Button onClick={() => setSlot(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={book}>Book slot</Button></>}>
        <div className="space-y-4">
          <FormField label="How many items" required>
            <Input inputMode="numeric" className="tnum" value={items}
              onChange={(e) => setItems(e.target.value)} />
          </FormField>
          <InlineAlert tone="info">
            {slot ? `${slot.remaining} place${slot.remaining === 1 ? '' : 's'} left in this slot.`
              : ''} Bookings are first come, first served.
          </InlineAlert>
        </div>
      </Modal>
    </>
  )
}
