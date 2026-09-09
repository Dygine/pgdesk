import { useState } from 'react'
import { ArrowLeftRight, BedDouble } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Select, Textarea, InlineAlert,
  StatusBadge, EmptyState, Skeleton,
} from '@/components/ui'
import { inr } from '@/lib/format'

/** Old bed released and new bed taken in one transaction, both rows locked. */
export default function Transfer() {
  const { activeBranchId } = useAuth()
  const { success, error } = useToast()
  const [residentId, setResidentId] = useState('')
  const [bedId, setBedId] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const residents = useApi(
    () => residentApi.list({ status: 'ACTIVE', branch_id: activeBranchId, page_size: 200 }),
    [activeBranchId])
  const beds = useApi(() => residentApi.availableBeds(activeBranchId), [activeBranchId],
    { initial: [] })

  const placed = (residents.data?.items || []).filter((r) => r.bed_id)
  const resident = placed.find((r) => r.id === residentId)

  const submit = async () => {
    if (!residentId || !bedId) return error('Choose a resident and a destination bed.')
    setBusy(true)
    try {
      const updated = await residentApi.transfer(residentId, bedId, reason || null)
      success(`${updated.full_name} moved`,
        `Now in room ${updated.placement.room}, bed ${updated.placement.bed_number}.`)
      setResidentId(''); setBedId(''); setReason('')
      residents.reload(); beds.reload()
    } catch (err) {
      error('Transfer failed', err.message)
    } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Transfer a resident"
        subtitle="Move someone to a different bed. The old bed is freed in the same step." />

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Move" subtitle="Only free beds in your branches are listed." />
          {residents.loading ? <div className="p-5"><Skeleton className="h-40" /></div> : (
            <div className="p-5 space-y-4">
              <FormField label="Resident" required>
                <Select value={residentId} onChange={(e) => setResidentId(e.target.value)}>
                  <option value="">Choose a resident…</option>
                  {placed.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name} — room {r.placement.room}, bed {r.placement.bed_number}
                    </option>
                  ))}
                </Select>
              </FormField>

              <FormField label="Destination bed" required>
                <Select value={bedId} onChange={(e) => setBedId(e.target.value)}>
                  <option value="">Choose a bed…</option>
                  {(beds.data || []).map((b) => (
                    <option key={b.id} value={b.id}>{b.label} — {inr(b.rent_amount)}</option>
                  ))}
                </Select>
              </FormField>

              <FormField label="Reason" hint="Recorded in the audit log.">
                <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)}
                  placeholder="Requested a quieter room" />
              </FormField>

              <Button variant="primary" icon={ArrowLeftRight} loading={busy}
                onClick={submit} className="w-full">Transfer resident</Button>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="What happens" />
          <div className="p-5 space-y-4">
            {resident ? (
              <div className="rounded-lg border border-line p-4">
                <p className="text-sm font-medium text-slate-900">{resident.full_name}</p>
                <div className="mt-3 flex items-center gap-3">
                  <div className="flex-1 rounded-lg bg-slate-50 p-3">
                    <p className="text-2xs text-slate-500">From</p>
                    <p className="text-sm text-slate-900">
                      Room {resident.placement.room} · bed {resident.placement.bed_number}
                    </p>
                    <StatusBadge status="Becomes available" tone="emerald" />
                  </div>
                  <ArrowLeftRight size={16} className="text-slate-400 shrink-0" />
                  <div className="flex-1 rounded-lg bg-brand-50 p-3">
                    <p className="text-2xs text-brand-700">To</p>
                    <p className="text-sm text-slate-900">
                      {(beds.data || []).find((b) => b.id === bedId)?.label || 'Not chosen'}
                    </p>
                    <StatusBadge status="Becomes occupied" tone="brand" />
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState icon={BedDouble} compact title="Choose a resident"
                message="Their current bed and the destination appear here." />
            )}

            <InlineAlert tone="info" title="Both beds are locked">
              The release and the assignment happen in one transaction, so a
              simultaneous booking of the destination bed cannot slip in between.
            </InlineAlert>
          </div>
        </Card>
      </div>
    </>
  )
}
