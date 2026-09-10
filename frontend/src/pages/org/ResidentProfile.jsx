import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, BedDouble, LogOut, ArrowLeftRight, ShieldCheck, ShieldX, Plus,
  IdCard, Receipt, CalendarCheck, MessageSquareWarning, RefreshCw, Pencil,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { invoiceApi } from '@/services/api/invoiceApi'
import { paymentApi } from '@/services/api/paymentApi'
import { attendanceApi } from '@/services/api/attendanceApi'
import { complaintApi } from '@/services/api/complaintApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, Skeleton,
  InlineAlert, Modal, FormField, Input, Select, Textarea, Tabs, Avatar, IconButton,
} from '@/components/ui'
import { inr, num, dateFmt, relative, timeFmt } from '@/lib/format'
import { PortalAccessCard, EditResidentModal } from './ResidentAccess'

const ID_TYPES = ['AADHAAR', 'PAN', 'PASSPORT', 'DRIVING_LICENCE', 'VOTER_ID', 'OTHER']

export default function ResidentProfile() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { can } = useAuth()
  const { success, error } = useToast()
  const [tab, setTab] = useState('overview')
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const resident = useApi(() => residentApi.get(id), [id])
  const kyc = useApi(() => residentApi.kyc(id), [id], { initial: [] })
  const beds = useApi(() => residentApi.availableBeds(), [], { enabled: modal === 'bed' })
  const invoices = useApi(() => invoiceApi.list({ resident_id: id, page_size: 50 }), [id],
    { enabled: can('invoices.view') })
  const payments = useApi(() => paymentApi.list({ resident_id: id, page_size: 50 }), [id],
    { enabled: can('payments.view') })
  const attendance = useApi(
    () => attendanceApi.list({ resident_id: id, page_size: 60 }), [id],
    { enabled: can('attendance.view') })
  const complaints = useApi(
    () => complaintApi.list({ resident_id: id, page_size: 50 }), [id],
    { enabled: can('complaints.view') })

  if (resident.error) {
    return (<><PageHeader title="Resident" />
      <InlineAlert tone="error" title="Could not load">{resident.error.message}</InlineAlert>
      <Button icon={ArrowLeft} className="mt-4"
        onClick={() => navigate('/app/residents')}>Back to residents</Button></>)
  }
  if (resident.loading && !resident.data) {
    return (<><PageHeader title="Resident" /><Skeleton className="h-64" /></>)
  }

  const r = resident.data
  const invoiceRows = invoices.data?.items || []
  const outstanding = invoiceRows
    .filter((i) => i.status !== 'CANCELLED')
    .reduce((a, i) => a + Number(i.balance || 0), 0)
  const openComplaints = (complaints.data?.items || [])
    .filter((c) => !['RESOLVED', 'CLOSED'].includes(c.status)).length
  const presentDays = (attendance.data?.items || [])
    .filter((a) => a.status === 'PRESENT').length

  const act = async (fn, message) => {
    setBusy(true)
    try {
      await fn()
      success(message)
      setModal(null)
      resident.reload(); kyc.reload()
    } catch (err) { error('That did not work', err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title={r.full_name}
        subtitle={r.placement?.room
          ? `Room ${r.placement.room} · bed ${r.placement.bed} · ${r.placement.branch}`
          : 'No bed assigned'}
        actions={<>
          <Button icon={ArrowLeft} onClick={() => navigate('/app/residents')}>Back</Button>
          <PermissionGuard perm="customers.edit">
            <Button icon={Pencil} onClick={() => setModal('edit')}>Edit</Button>
          </PermissionGuard>
          {!r.bed_id && r.status !== 'CHECKED_OUT' && (
            <PermissionGuard perm={['customers.assign_bed', 'beds.assign']}>
              <Button variant="primary" icon={BedDouble}
                onClick={() => { setF({}); setModal('bed') }}>Assign a bed</Button>
            </PermissionGuard>
          )}
          {r.bed_id && (
            <PermissionGuard perm="customers.transfer">
              <Button icon={ArrowLeftRight}
                onClick={() => navigate('/app/transfer')}>Transfer</Button>
            </PermissionGuard>
          )}
        </>} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Monthly rent" value={inr(r.monthly_rent)} tone="brand"
          sub={`Due on the ${r.rent_due_day}th`} />
        <StatCard label="Outstanding" value={inr(outstanding)} icon={Receipt}
          tone={outstanding > 0 ? 'amber' : 'emerald'} />
        <StatCard label="Days present" value={num(presentDays)} icon={CalendarCheck}
          tone="violet" sub="last 60 records" />
        <StatCard label="Open complaints" value={num(openComplaints)}
          icon={MessageSquareWarning} tone={openComplaints ? 'rose' : 'slate'} />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'overview', label: 'Overview' },
        { value: 'kyc', label: 'Documents', count: (kyc.data || []).length },
        { value: 'money', label: 'Invoices & payments', count: invoiceRows.length },
        { value: 'activity', label: 'Activity' },
      ]} />

      <div className="mt-4">
        {tab === 'overview' && (
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Personal"
                action={<StatusBadge status={r.status} dot />} />
              <div className="p-5 flex items-start gap-4">
                <Avatar name={r.full_name} size="lg" />
                <dl className="flex-1 space-y-2">
                  {[['Phone', r.phone], ['Alternate', r.alternate_phone],
                    ['Email', r.email], ['Gender', r.gender],
                    ['Date of birth', r.date_of_birth ? dateFmt(r.date_of_birth) : null],
                    ['Occupation', r.occupation],
                    ['Address', [r.address, r.city, r.state, r.pincode]
                      .filter(Boolean).join(', ')]].map(([k, v]) => (
                    <div key={k} className="grid grid-cols-3 gap-2">
                      <dt className="text-xs text-slate-500">{k}</dt>
                      <dd className="col-span-2 text-sm text-slate-800 break-words">{v || '—'}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </Card>

            <Card>
              <CardHeader title="Stay & emergency contact" />
              <dl className="divide-y divide-line">
                {[['Branch', r.placement?.branch], ['Building', r.placement?.building],
                  ['Floor', r.placement?.floor], ['Room', r.placement?.room],
                  ['Bed', r.placement?.bed],
                  ['Joined', r.joining_date ? dateFmt(r.joining_date) : null],
                  ['Expected checkout', r.expected_checkout_date
                    ? dateFmt(r.expected_checkout_date) : null],
                  ['Deposit', inr(r.security_deposit)],
                  ['Emergency contact', r.emergency_contact_name
                    ? `${r.emergency_contact_name} (${r.emergency_contact_relation || 'contact'}) · ${r.emergency_contact_phone || ''}`
                    : null],
                  ['App login', r.has_portal_login
                    ? (r.must_change_password ? 'Waiting for first sign-in' : 'Active')
                    : 'Not set up'],
                  ['Gate QR', r.has_qr ? 'Issued' : 'Not issued']].map(([k, v]) => (
                  <div key={k} className="px-5 py-2.5 grid grid-cols-3 gap-3">
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="col-span-2 text-sm text-slate-800">{v || '—'}</dd>
                  </div>
                ))}
              </dl>
              <div className="px-5 py-4 border-t border-line flex flex-wrap gap-2">
                <PermissionGuard perm="customers.edit">
                  <Button size="sm" icon={RefreshCw}
                    onClick={() => act(() => residentApi.reissueQr(r.id),
                      'A new gate QR has been issued')}>Reissue QR</Button>
                </PermissionGuard>
                {r.status !== 'CHECKED_OUT' && (
                  <PermissionGuard perm="customers.checkout">
                    <Button size="sm" icon={LogOut}
                      onClick={() => navigate('/app/checkout')}>Check out</Button>
                  </PermissionGuard>
                )}
              </div>
            </Card>

            <PortalAccessCard resident={r} onChanged={resident.reload} />

            {r.notes && (
              <Card className="lg:col-span-2">
                <CardHeader title="Notes" />
                <p className="p-5 text-sm text-slate-700 whitespace-pre-line">{r.notes}</p>
              </Card>
            )}
          </div>
        )}

        {tab === 'kyc' && (
          <Card>
            <CardHeader title="Identity documents"
              subtitle={can('customers.kyc_view')
                ? 'You can see full numbers.'
                : 'Numbers are masked — full numbers need the KYC view permission.'}
              action={<PermissionGuard perm="customers.edit">
                <Button size="sm" icon={Plus}
                  onClick={() => { setF({ id_type: 'AADHAAR' }); setModal('kyc') }}>
                  Add document</Button>
              </PermissionGuard>} />
            {(kyc.data || []).length === 0 ? (
              <EmptyState icon={IdCard} title="Nothing on file"
                message="Record an Aadhaar, PAN or passport for this resident." />
            ) : (
              <div className="divide-y divide-line">
                {kyc.data.map((k) => (
                  <div key={k.id} className="px-5 py-3.5 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900">
                        {k.id_type.replace('_', ' ')}</p>
                      <p className="text-sm text-slate-600 font-mono">{k.id_number}</p>
                      {k.masked && (
                        <p className="text-2xs text-slate-400">
                          Masked — the full number never leaves the server for your role.
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusBadge status={k.status}
                        tone={k.status === 'VERIFIED' ? 'emerald'
                          : k.status === 'REJECTED' ? 'rose' : 'amber'} dot />
                      {k.status !== 'VERIFIED' && (
                        <PermissionGuard perm="customers.kyc_verify">
                          <IconButton icon={ShieldCheck} label="Verify"
                            onClick={() => act(() => residentApi.verifyKyc(k.id, true),
                              'Document verified')} />
                          <IconButton icon={ShieldX} label="Reject" tone="danger"
                            onClick={() => act(() => residentApi.verifyKyc(k.id, false),
                              'Document rejected')} />
                        </PermissionGuard>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {tab === 'money' && (
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Invoices" subtitle={`${invoiceRows.length} raised`} />
              {invoiceRows.length === 0 ? (
                <EmptyState icon={Receipt} compact title="No invoices" />
              ) : (
                <div className="divide-y divide-line max-h-[480px] overflow-y-auto">
                  {invoiceRows.map((i) => (
                    <div key={i.id} className="px-5 py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-slate-900">{i.invoice_number}</p>
                        <p className="text-2xs text-slate-500 tnum">
                          Due {dateFmt(i.due_date)}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm tnum text-slate-900">{inr(i.total)}</p>
                        <StatusBadge status={i.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card>
              <CardHeader title="Payments"
                subtitle={`${(payments.data?.items || []).length} recorded`} />
              {(payments.data?.items || []).length === 0 ? (
                <EmptyState compact title="No payments" />
              ) : (
                <div className="divide-y divide-line max-h-[480px] overflow-y-auto">
                  {payments.data.items.map((p) => (
                    <div key={p.id} className="px-5 py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm text-slate-900">{p.payment_number}</p>
                        <p className="text-2xs text-slate-500 tnum">
                          {dateFmt(p.payment_date)} · {p.method.replace('_', ' ')}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-sm tnum text-slate-900">{inr(p.amount)}</p>
                        <StatusBadge status={p.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {tab === 'activity' && (
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader title="Attendance" subtitle="Most recent first" />
              {(attendance.data?.items || []).length === 0 ? (
                <EmptyState icon={CalendarCheck} compact title="Nothing recorded" />
              ) : (
                <div className="divide-y divide-line max-h-[480px] overflow-y-auto">
                  {attendance.data.items.map((a) => (
                    <div key={a.id} className="px-5 py-2.5 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm text-slate-800 tnum">{dateFmt(a.on_date)}</p>
                        <p className="text-2xs text-slate-500">
                          {a.check_in_at ? `In ${timeFmt(a.check_in_at)}` : 'No entry time'}
                          {a.source === 'gate' ? ' · gate' : ''}
                        </p>
                      </div>
                      <StatusBadge status={a.status.replace('_', ' ')}
                        tone={a.status === 'PRESENT' ? 'emerald'
                          : a.status === 'ABSENT' ? 'rose' : 'amber'} dot />
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Card>
              <CardHeader title="Complaints" />
              {(complaints.data?.items || []).length === 0 ? (
                <EmptyState icon={MessageSquareWarning} compact title="Nothing reported" />
              ) : (
                <div className="divide-y divide-line max-h-[480px] overflow-y-auto">
                  {complaints.data.items.map((c) => (
                    <div key={c.id} className="px-5 py-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm text-slate-900 truncate">{c.subject}</p>
                          <p className="text-2xs text-slate-500">
                            {c.ticket_number} · {relative(c.created_at)}</p>
                        </div>
                        <StatusBadge status={c.status.replace('_', ' ')} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>

      <EditResidentModal resident={r} open={modal === 'edit'} onClose={() => setModal(null)}
        onSaved={() => { setModal(null); resident.reload() }} />

      <Modal open={modal === 'bed'} onClose={() => setModal(null)} size="sm"
        title="Assign a bed" subtitle="Only beds that are free right now are listed."
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!f.bed_id}
            onClick={() => act(() => residentApi.assignBed(r.id, f.bed_id),
              'Bed assigned')}>Assign bed</Button></>}>
        <FormField label="Bed" required>
          <Select value={f.bed_id || ''} onChange={(e) => setF({ ...f, bed_id: e.target.value })}>
            <option value="">Choose…</option>
            {(beds.data || []).map((b) => (
              <option key={b.id} value={b.id}>{b.label} — {inr(b.rent_amount)}</option>
            ))}
          </Select>
        </FormField>
      </Modal>

      <Modal open={modal === 'kyc'} onClose={() => setModal(null)} size="sm"
        title="Record a document"
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy}
            onClick={() => act(() => residentApi.addKyc(r.id, {
              id_type: f.id_type, id_number: f.id_number,
              document_reference: f.document_reference || null,
              notes: f.notes || null }), 'Document recorded')}>Save</Button></>}>
        <div className="space-y-4">
          <FormField label="Type" required>
            <Select value={f.id_type || 'AADHAAR'}
              onChange={(e) => setF({ ...f, id_type: e.target.value })}>
              {ID_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </Select>
          </FormField>
          <FormField label="Number" required>
            <Input value={f.id_number || ''} className="font-mono"
              onChange={(e) => setF({ ...f, id_number: e.target.value })} />
          </FormField>
          <FormField label="Document reference" hint="Where the scan is filed.">
            <Input value={f.document_reference || ''}
              onChange={(e) => setF({ ...f, document_reference: e.target.value })} />
          </FormField>
          <InlineAlert tone="info">
            The number is stored apart from the resident record and never appears in
            lists, reports or the audit log.
          </InlineAlert>
        </div>
      </Modal>
    </>
  )
}
