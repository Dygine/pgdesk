/**
 * Accounts: a simple profit and loss.
 *
 * Money that came in (verified payments) minus money that went out (expenses,
 * salaries included) for a period. Deposits, tax and capital purchases are
 * shown separately and never counted as profit - a deposit is owed back, so
 * counting it would make move-in months look like windfalls.
 */
import { useMemo, useState } from 'react'
import { Download, TrendingUp, TrendingDown, Scale, Info } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { accountsApi } from '@/services/api/accountsApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, FormField, Input, InlineAlert, Skeleton, EmptyState,
} from '@/components/ui'
import { inr } from '@/lib/format'

/** Local calendar date. `iso()` goes through toISOString, which is UTC: in
 *  India "1 September, midnight" becomes "31 August" and every range slips. */
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

const cx = (...a) => a.filter(Boolean).join(' ')

function range(key) {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  switch (key) {
    case 'last-month': return [new Date(y, m - 1, 1), new Date(y, m, 0)]
    case 'quarter': {
      const q = Math.floor(m / 3) * 3
      return [new Date(y, q, 1), now]
    }
    case 'year': {
      // Indian financial year: April to March.
      const start = m >= 3 ? new Date(y, 3, 1) : new Date(y - 1, 3, 1)
      return [start, now]
    }
    default: return [new Date(y, m, 1), now]
  }
}

const PERIODS = [
  ['this-month', 'This month'], ['last-month', 'Last month'],
  ['quarter', 'This quarter'], ['year', 'This financial year'], ['custom', 'Custom'],
]

export default function Accounts() {
  const { activeBranchId } = useAuth()
  const { error } = useToast()
  const [period, setPeriod] = useState('this-month')
  const [custom, setCustom] = useState(() => {
    const [a, b] = range('this-month')
    return { from: ymd(a), to: ymd(b) }
  })
  const [exporting, setExporting] = useState(false)

  const params = useMemo(() => {
    if (period === 'custom') return { from_date: custom.from, to_date: custom.to }
    const [a, b] = range(period)
    return { from_date: ymd(a), to_date: ymd(b) }
  }, [period, custom])

  const pnl = useApi(() => accountsApi.pnl({ ...params, branch_id: activeBranchId }),
    [params.from_date, params.to_date, activeBranchId])
  const d = pnl.data

  const download = async () => {
    setExporting(true)
    try { await accountsApi.downloadCsv({ ...params, branch_id: activeBranchId }) }
    catch (err) { error('Export failed', err.message) }
    finally { setExporting(false) }
  }

  const maxTrend = d ? Math.max(1, ...d.trend.flatMap((t) => [t.income, t.expenses])) : 1
  const maxExpense = d ? Math.max(1, ...d.expenses.lines.map((l) => l.amount)) : 1
  const profit = d?.net_profit ?? 0

  return (
    <>
      <PageHeader title="Accounts"
        subtitle="Money in, money out, and what is left - for any period."
        actions={<PermissionGuard perm="reports.export">
          <Button icon={Download} loading={exporting} onClick={download} disabled={!d}>
            Export CSV</Button>
        </PermissionGuard>} />

      <Card className="mb-4">
        <div className="p-3 sm:p-4 flex flex-col lg:flex-row lg:items-end gap-3">
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1">
            {PERIODS.map(([k, label]) => (
              <button key={k} onClick={() => setPeriod(k)}
                className={cx('h-9 px-3 rounded-lg text-sm whitespace-nowrap border transition-colors',
                  period === k ? 'bg-brand-700 text-white border-brand-700'
                    : 'bg-white text-slate-700 border-line hover:bg-slate-50')}>
                {label}
              </button>
            ))}
          </div>
          {period === 'custom' && (
            <div className="grid grid-cols-2 gap-3 lg:ml-auto lg:w-80">
              <FormField label="From">
                <Input type="date" value={custom.from} max={custom.to}
                  onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
              </FormField>
              <FormField label="To">
                <Input type="date" value={custom.to} min={custom.from}
                  onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
              </FormField>
            </div>
          )}
        </div>
      </Card>

      {pnl.error ? (
        <InlineAlert tone="error" title="Could not load the accounts">{pnl.error.message}</InlineAlert>
      ) : !d ? <Skeleton className="h-72" /> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
            <StatCard label="Income collected" value={inr(d.income.total)} icon={TrendingUp}
              tone="emerald" sub={`${inr(d.income.billed_total)} billed`} />
            <StatCard label="Expenses" value={inr(d.expenses.total)} icon={TrendingDown} tone="rose" />
            <StatCard label={profit >= 0 ? 'Net profit' : 'Net loss'} value={inr(Math.abs(profit))}
              icon={Scale} tone={profit >= 0 ? 'brand' : 'rose'}
              sub={d.income.total ? `${d.margin_pct}% of income` : undefined} />
            <StatCard label="Still to collect" value={inr(d.receivable_now)} tone="amber"
              sub="all unpaid invoices, today" />
          </div>

          <div className="grid lg:grid-cols-2 gap-4 mb-4">
            <Card>
              <CardHeader title="Income" subtitle="Collected is what actually came in. Billed is for comparison." />
              {d.income.lines.length === 0 ? (
                <EmptyState compact title="No income in this period" />
              ) : (
                <div className="px-4 sm:px-5 py-2">
                  <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 text-2xs text-slate-500 pb-2 border-b border-line">
                    <span>Type</span><span className="text-right w-24">Collected</span>
                    <span className="text-right w-24">Billed</span>
                  </div>
                  {d.income.lines.map((l) => (
                    <div key={l.kind} className="grid grid-cols-[1fr_auto_auto] gap-x-4 py-2.5 border-b border-line last:border-0 text-sm">
                      <span className="text-slate-800 min-w-0 truncate">{l.label}</span>
                      <span className="text-right w-24 tnum font-medium text-slate-900">{inr(l.collected)}</span>
                      <span className="text-right w-24 tnum text-slate-500">{inr(l.billed)}</span>
                    </div>
                  ))}
                  <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 py-3 text-sm font-semibold">
                    <span className="text-slate-900">Total</span>
                    <span className="text-right w-24 tnum text-emerald-700">{inr(d.income.total)}</span>
                    <span className="text-right w-24 tnum text-slate-600">{inr(d.income.billed_total)}</span>
                  </div>
                </div>
              )}
            </Card>

            <Card>
              <CardHeader title="Expenses" subtitle="Everything recorded under Expenses, salaries included." />
              {d.expenses.lines.length === 0 ? (
                <EmptyState compact title="No expenses in this period" />
              ) : (
                <div className="px-4 sm:px-5 py-3 space-y-3">
                  {d.expenses.lines.map((l) => (
                    <div key={l.category}>
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-slate-800 truncate">{l.category}
                          <span className="text-2xs text-slate-400 ml-1.5">{l.count} {l.count === 1 ? 'entry' : 'entries'}</span></span>
                        <span className="tnum font-medium text-slate-900 shrink-0">{inr(l.amount)}</span>
                      </div>
                      <div className="h-1.5 mt-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full rounded-full bg-rose-400"
                          style={{ width: `${(l.amount / maxExpense) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                  <div className="flex justify-between pt-2 border-t border-line text-sm font-semibold">
                    <span className="text-slate-900">Total</span>
                    <span className="tnum text-rose-700">{inr(d.expenses.total)}</span>
                  </div>
                </div>
              )}
            </Card>
          </div>

          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
            <Card>
              <CardHeader title="Last six months" subtitle="Income against expenses, month by month." />
              <div className="p-4 sm:p-5">
                <div className="flex items-end gap-2 sm:gap-4 h-44">
                  {d.trend.map((t) => (
                    <div key={t.month} className="flex-1 min-w-0 flex flex-col items-center gap-1.5">
                      <div className="w-full flex items-end justify-center gap-1 h-36">
                        <div title={`Income ${inr(t.income)}`} className="w-1/3 max-w-[18px] rounded-t bg-emerald-500"
                          style={{ height: `${(t.income / maxTrend) * 100}%` }} />
                        <div title={`Expenses ${inr(t.expenses)}`} className="w-1/3 max-w-[18px] rounded-t bg-rose-400"
                          style={{ height: `${(t.expenses / maxTrend) * 100}%` }} />
                      </div>
                      <span className="text-2xs text-slate-500 whitespace-nowrap">{t.label.split(' ')[0]}</span>
                      <span className={cx('text-2xs tnum font-medium', t.profit >= 0 ? 'text-slate-700' : 'text-rose-600')}>
                        {t.profit >= 0 ? '' : '−'}{inr(Math.abs(t.profit), { compact: true })}</span>
                    </div>
                  ))}
                </div>
                <div className="flex gap-4 mt-3 text-2xs text-slate-500">
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-emerald-500" />Income</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-rose-400" />Expenses</span>
                  <span>Figure under each month is the profit.</span>
                </div>
              </div>
            </Card>

            <Card>
              <CardHeader title="Kept out of profit" subtitle="Real money, but not earnings." />
              <div className="px-4 sm:px-5 py-2 divide-y divide-line">
                {[
                  ['Deposits collected', d.not_in_profit.deposits_collected, 'Refundable, so owed back to residents.'],
                  ['Tax collected', d.not_in_profit.tax_collected, 'Owed onward, not earned.'],
                  ['Assets bought', d.not_in_profit.assets_bought, 'Capital - from the Assets register.'],
                  ['Stock added', d.not_in_profit.stock_added, 'Inventory at purchase price.'],
                ].map(([label, value, hint]) => (
                  <div key={label} className="py-2.5 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm text-slate-800">{label}</p>
                      <p className="text-2xs text-slate-500">{hint}</p>
                    </div>
                    <span className="text-sm tnum font-medium text-slate-900 shrink-0">{inr(value)}</span>
                  </div>
                ))}
              </div>
              <div className="px-4 sm:px-5 pb-4">
                <p className="text-2xs text-slate-500 flex gap-1.5">
                  <Info size={13} className="shrink-0 mt-px" />
                  If a supplier bill for stock should count against profit, record it under Expenses.
                </p>
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  )
}
