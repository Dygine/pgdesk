import { useState } from 'react'
import { QrCode, LogIn, LogOut, ScanLine, TriangleAlert } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { scanApi } from '@/services/api/scanApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Input, Select, StatusBadge, EmptyState,
  InlineAlert, Skeleton, StatCard,
} from '@/components/ui'
import { num, dateTimeFmt, relative } from '@/lib/format'

const RESULT_TONE = { ok: 'emerald', duplicate: 'amber', invalid: 'rose',
  checked_out: 'rose', inactive: 'rose', wrong_branch: 'rose' }

/**
 * The gate desk. A refusal is shown as a result rather than an error, because
 * the guard needs to see who was refused and why.
 */
export default function Scan() {
  const { activeBranchId } = useAuth()
  const { error } = useToast()
  const [token, setToken] = useState('')
  const [direction, setDirection] = useState('')
  const [gate, setGate] = useState('Main gate')
  const [last, setLast] = useState(null)
  const [busy, setBusy] = useState(false)

  const logs = useApi(
    () => scanApi.logs({ branch_id: activeBranchId, page_size: 30 }),
    [activeBranchId, last])

  const submit = async (e) => {
    e?.preventDefault()
    if (!token.trim()) return
    setBusy(true)
    try {
      const result = await scanApi.scan(token.trim(), direction || null, gate || null)
      setLast(result)
      setToken('')
    } catch (err) {
      error('Scan failed', err.message)
    } finally { setBusy(false) }
  }

  const rows = logs.data?.items || []
  const todayEntries = rows.filter((g) => g.direction === 'ENTRY').length

  return (
    <>
      <PageHeader title="Gate scan"
        subtitle="Scan or type a resident's QR token to record entry and exit." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Movements shown" value={num(rows.length)} icon={ScanLine} tone="brand" />
        <StatCard label="Entries" value={num(todayEntries)} icon={LogIn} tone="emerald" />
        <StatCard label="Exits" value={num(rows.length - todayEntries)}
          icon={LogOut} tone="slate" />
        <StatCard label="Refused"
          value={num(rows.filter((g) => !g.allowed).length)}
          icon={TriangleAlert} tone="rose" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Scan" subtitle="Direction is worked out automatically." />
          <form onSubmit={submit} className="p-5 space-y-4">
            <FormField label="QR token" required
              hint="Scanners type the token straight into this box.">
              <Input value={token} autoFocus onChange={(e) => setToken(e.target.value)}
                placeholder="Scan or paste the code" className="font-mono" />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Direction" hint="Leave on auto unless correcting.">
                <Select value={direction} onChange={(e) => setDirection(e.target.value)}>
                  <option value="">Automatic</option>
                  <option value="ENTRY">Entry</option>
                  <option value="EXIT">Exit</option>
                </Select>
              </FormField>
              <FormField label="Gate">
                <Input value={gate} onChange={(e) => setGate(e.target.value)} />
              </FormField>
            </div>
            <Button type="submit" variant="primary" icon={QrCode} loading={busy}
              className="w-full">Record scan</Button>
          </form>

          {last && (
            <div className="px-5 pb-5">
              <div className={`rounded-lg border p-4 ${
                last.allowed ? 'border-emerald-200 bg-emerald-50'
                  : 'border-rose-200 bg-rose-50'}`}>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <p className="text-sm font-semibold text-slate-900">
                    {last.resident?.name || 'Unknown code'}
                  </p>
                  <StatusBadge status={last.allowed ? last.direction || 'OK' : 'Refused'}
                    tone={RESULT_TONE[last.result] || 'slate'} />
                </div>
                <p className="text-sm text-slate-700">{last.message}</p>
                {last.resident && (
                  <p className="text-2xs text-slate-500 tnum mt-1">
                    {last.resident.room ? `Room ${last.resident.room}` : 'No room'}
                    {last.resident.bed ? ` · bed ${last.resident.bed}` : ''}
                    {` · ${last.resident.status}`}
                  </p>
                )}
              </div>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Recent movements" subtitle="Newest first" />
          {logs.loading && !logs.data ? (
            <div className="p-4 space-y-2">{[0, 1, 2].map((i) =>
              <Skeleton key={i} className="h-12" />)}</div>
          ) : rows.length === 0 ? (
            <EmptyState icon={ScanLine} compact title="Nothing recorded yet"
              message="Scans appear here as they happen." />
          ) : (
            <div className="divide-y divide-line max-h-[560px] overflow-y-auto">
              {rows.map((g) => (
                <div key={g.id} className="px-5 py-3 flex items-center gap-3">
                  <span className={`h-8 w-8 rounded-lg inline-flex items-center justify-center shrink-0 ${
                    !g.allowed ? 'bg-rose-50 text-rose-600'
                      : g.direction === 'ENTRY' ? 'bg-emerald-50 text-emerald-600'
                        : 'bg-slate-100 text-slate-500'}`}>
                    {g.direction === 'ENTRY' ? <LogIn size={15} /> : <LogOut size={15} />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-800 truncate">{g.resident || 'Unknown'}</p>
                    <p className="text-2xs text-slate-500 tnum">
                      {dateTimeFmt(g.occurred_at)}{g.gate ? ` · ${g.gate}` : ''}
                      {g.reason ? ` · ${g.reason}` : ''}
                    </p>
                  </div>
                  {!g.allowed && <StatusBadge status="Refused" tone="rose" />}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
