import { IndianRupee, Receipt, Wallet } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, Skeleton, InlineAlert, DataTable,
} from '@/components/ui'
import { inr, dateFmt } from '@/lib/format'

export default function MyRent() {
  const { data, loading, error } = useApi(() => meApi.rent(), [])

  if (error) {
    return (<><PageHeader title="My rent" />
      <InlineAlert tone="error" title="Could not load">{error.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="My rent" /><Skeleton className="h-64" /></>)
  }

  const s = data.summary

  return (
    <>
      <PageHeader title="My rent" subtitle="Everything you have been billed and paid." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Monthly rent" value={inr(s.monthly_rent)}
          icon={IndianRupee} tone="brand" sub={`Due on the ${s.rent_due_day}th`} />
        <StatCard label="Outstanding" value={inr(s.outstanding)}
          tone={s.outstanding > 0 ? 'amber' : 'emerald'} />
        <StatCard label="Paid this year" value={inr(s.paid_this_year)}
          icon={Wallet} tone="emerald" />
        <StatCard label="Deposit held" value={inr(s.security_deposit)} tone="slate" />
      </div>

      {s.outstanding > 0 && (
        <InlineAlert tone="warn" className="mb-4" title={`${inr(s.outstanding)} outstanding`}>
          Pay at the front desk or by UPI. A payment shows here as pending until the
          office confirms it.
        </InlineAlert>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader title="Invoices" subtitle={`${data.invoices.length} shown`} />
          {data.invoices.length === 0 ? (
            <EmptyState icon={Receipt} compact title="No invoices yet" />
          ) : (
            <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
              {data.invoices.map((i) => (
                <div key={i.id} className="px-5 py-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-900">{i.invoice_number}</p>
                      <p className="text-2xs text-slate-500 tnum">
                        Due {dateFmt(i.due_date)}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-semibold text-slate-900 tnum">{inr(i.total)}</p>
                      <StatusBadge status={i.status} />
                    </div>
                  </div>
                  <ul className="mt-2 space-y-0.5">
                    {i.items.map((it, n) => (
                      <li key={n} className="flex justify-between text-2xs text-slate-500">
                        <span className="truncate">{it.description}</span>
                        <span className="tnum shrink-0">{inr(it.amount)}</span>
                      </li>
                    ))}
                  </ul>
                  {Number(i.balance) > 0 && (
                    <p className="text-xs text-amber-700 tnum mt-1.5">
                      {inr(i.balance)} still due
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Payments" subtitle="Pending means the office has not confirmed it yet" />
          {data.payments.length === 0 ? (
            <EmptyState icon={Wallet} compact title="No payments recorded" />
          ) : (
            <div className="divide-y divide-line max-h-[520px] overflow-y-auto">
              {data.payments.map((p) => (
                <div key={p.id} className="px-5 py-3.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">{p.payment_number}</p>
                    <p className="text-2xs text-slate-500 tnum">
                      {dateFmt(p.payment_date)} · {p.method.replace('_', ' ')}
                      {p.reference ? ` · ${p.reference}` : ''}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-semibold text-slate-900 tnum">{inr(p.amount)}</p>
                    <StatusBadge status={p.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
