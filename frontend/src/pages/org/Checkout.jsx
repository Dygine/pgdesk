import { useState } from 'react'
import { LogOut, TriangleAlert } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { invoiceApi } from '@/services/api/invoiceApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Select, Input, Textarea, InlineAlert,
  StatusBadge, EmptyState, Skeleton, ConfirmDialog,
} from '@/components/ui'
import { inr, dateFmt, today } from '@/lib/format'

export default function Checkout() {
  const { activeBranchId } = useAuth()
  const { success, error } = useToast()
  const [residentId, setResidentId] = useState('')
  const [checkoutDate, setCheckoutDate] = useState(today())
  const [notes, setNotes] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  const residents = useApi(
    () => residentApi.list({ status: 'live', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId])
  const dues = useApi(
    () => (residentId ? invoiceApi.list({ resident_id: residentId, page_size: 50 })
      : Promise.resolve({ items: [] })),
    [residentId])

  const rows = residents.data?.items || []
  const resident = rows.find((r) => r.id === residentId)
  const outstanding = (dues.data?.items || [])
    .filter((i) => i.status !== 'CANCELLED')
    .reduce((a, i) => a + Number(i.balance || 0), 0)

  const submit = async () => {
    setBusy(true)
    try {
      await residentApi.checkout(residentId, {
        checkout_date: checkoutDate || null, notes: notes || null,
      })
      success(`${resident.full_name} checked out`, 'Their bed is available again.')
      setResidentId(''); setNotes(''); setConfirm(false)
      residents.reload()
    } catch (err) {
      error('Checkout failed', err.message)
    } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Checkout"
        subtitle="Close a stay and release the bed back into inventory." />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Check someone out" />
          {residents.loading ? <div className="p-5"><Skeleton className="h-40" /></div> : (
            <div className="p-5 space-y-4">
              <FormField label="Resident" required>
                <Select value={residentId} onChange={(e) => setResidentId(e.target.value)}>
                  <option value="">Choose a resident…</option>
                  {rows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name}{r.placement?.room ? ` — room ${r.placement.room}` : ''}
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
                disabled={!residentId} onClick={() => setConfirm(true)}>
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
                message="Their bed and any unpaid invoices appear here." />
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
                    <StatusBadge status={resident.status} dot />
                    <span className="text-xs text-slate-500 tnum">
                      Joined {resident.joining_date ? dateFmt(resident.joining_date) : '—'}
                    </span>
                  </div>
                </div>

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
    </>
  )
}
