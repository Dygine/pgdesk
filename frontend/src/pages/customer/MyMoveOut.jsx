/**
 * Moving out: the resident tells the PG ahead of time.
 *
 * PGs run on a notice period (usually a month). Giving notice here records the
 * date, tells the office, and shows whether it is short of the PG's notice
 * period - which matters because the deposit is normally settled against it.
 * Until the date passes the resident can change their mind and withdraw.
 */
import { useState } from 'react'
import { CalendarClock, Undo2, Send, ShieldCheck } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Input, Textarea, InlineAlert, Skeleton,
  StatusBadge, ConfirmDialog,
} from '@/components/ui'
import { inr, dateFmt } from '@/lib/format'

const localDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return localDate(d) }
const daysFromToday = (ymd) => Math.round((new Date(`${ymd}T00:00:00`) - new Date(new Date().toDateString())) / 86400000)

const STATUS_TEXT = {
  SUBMITTED: ['Sent - waiting for the office', 'amber'],
  ACKNOWLEDGED: ['Confirmed by the office', 'emerald'],
  WITHDRAWN: ['Withdrawn', 'slate'], CANCELLED: ['Cancelled by the office', 'slate'],
  COMPLETED: ['Completed', 'slate'],
}

export default function MyMoveOut() {
  const { success, error } = useToast()
  const { data, loading, error: failed, reload } = useApi(() => meApi.notice(), [])
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)       // 'give' | 'withdraw'

  if (failed) {
    return (<><PageHeader title="Moving out" />
      <InlineAlert tone="error" title="Could not load">{failed.message}</InlineAlert></>)
  }
  if (loading && !data) return (<><PageHeader title="Moving out" /><Skeleton className="h-64" /></>)

  const required = data.notice_days
  const chosen = date || plusDays(required)
  const given = daysFromToday(chosen)
  const short = given < required
  const notice = data.notice

  const give = async () => {
    setBusy(true)
    try {
      await meApi.giveNotice({ planned_checkout_date: chosen, reason: reason.trim() || null })
      success('Notice sent', 'The office has been told your moving-out date.')
      setConfirm(null); setReason(''); setDate('')
      reload()
    } catch (err) { error('Could not send your notice', err.message) }
    finally { setBusy(false) }
  }
  const withdraw = async () => {
    setBusy(true)
    try {
      await meApi.withdrawNotice()
      success('Notice withdrawn', 'Your stay carries on as normal.')
      setConfirm(null)
      reload()
    } catch (err) { error('Could not withdraw', err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Moving out"
        subtitle={`Let the PG know ahead of time. This PG asks for ${required} days' notice.`} />

      {notice ? (
        <Card className="max-w-2xl">
          <div className="p-5 sm:p-6">
            <div className="flex items-start gap-4">
              <span className="h-12 w-12 rounded-xl bg-brand-50 text-brand-700 inline-flex items-center justify-center shrink-0">
                <CalendarClock size={22} />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-slate-500">You are moving out on</p>
                <p className="text-2xl font-semibold text-slate-900 tnum">{dateFmt(notice.planned_checkout_date)}</p>
                <p className="text-sm text-slate-600 mt-1">
                  {notice.days_left > 0 ? `${notice.days_left} days from today` : notice.days_left === 0 ? 'Today' : 'The date has passed'}
                </p>
                <div className="flex gap-2 flex-wrap mt-3">
                  <StatusBadge status={STATUS_TEXT[notice.status]?.[0] || notice.status}
                    tone={STATUS_TEXT[notice.status]?.[1]} dot />
                  {notice.short_notice && <StatusBadge status="Short notice" tone="rose" />}
                </div>
              </div>
            </div>
            {notice.office_note && (
              <InlineAlert tone="info" className="mt-5" title="From the office">{notice.office_note}</InlineAlert>
            )}
            {notice.short_notice && (
              <InlineAlert tone="warn" className="mt-4" title={`${notice.days_given} days' notice given, ${notice.notice_days_required} asked for`}>
                The PG may settle part of your deposit ({inr(data.security_deposit)}) against the
                shortfall. Talk to the office if you have not already.
              </InlineAlert>
            )}
            <p className="text-xs text-slate-500 mt-5">
              Until then everything carries on as normal - your bed, your gate QR and your rent.
            </p>
            {notice.days_left >= 0 && (
              <Button className="mt-4" icon={Undo2} onClick={() => setConfirm('withdraw')}>
                I am not moving out after all</Button>
            )}
          </div>
        </Card>
      ) : !data.can_give ? (
        <InlineAlert tone="info" title="Notice is not available">
          Notice can be given by residents who are currently staying at the PG.
        </InlineAlert>
      ) : (
        <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4 max-w-4xl">
          <Card>
            <CardHeader title="Give notice" subtitle="The office sees this straight away." />
            <div className="p-5 space-y-4">
              <FormField label="Last day at the PG" required
                hint={`${required} days from today is ${dateFmt(plusDays(required))}.`}>
                <Input type="date" min={plusDays(0)} max={plusDays(365)} value={chosen}
                  onChange={(e) => setDate(e.target.value)} />
              </FormField>
              {short ? (
                <InlineAlert tone="warn" title={`That is ${given} day${given === 1 ? '' : 's'}' notice`}>
                  Less than the {required} days this PG asks for. You can still send it; the
                  office may settle part of your deposit against the difference.
                </InlineAlert>
              ) : (
                <InlineAlert tone="success" icon={ShieldCheck} title={`${given} days' notice`}>
                  That meets the PG's notice period.
                </InlineAlert>
              )}
              <FormField label="Reason" hint="Optional - it helps the office plan.">
                <Textarea rows={2} value={reason} maxLength={300}
                  onChange={(e) => setReason(e.target.value)} placeholder="New job in another city" />
              </FormField>
              <Button variant="primary" icon={Send} className="w-full" onClick={() => setConfirm('give')}>
                Send notice</Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="What happens next" />
            <ol className="p-5 space-y-3 text-sm text-slate-600 list-decimal list-inside marker:text-slate-400">
              <li>The office is told and confirms your date.</li>
              <li>You keep your bed and your gate QR until the day.</li>
              <li>You can withdraw any time before the date.</li>
              <li>On the day, the office checks you out and settles your deposit of {inr(data.security_deposit)}.</li>
            </ol>
            {data.last && (
              <p className="px-5 pb-5 text-2xs text-slate-500">
                Your last notice ({dateFmt(data.last.planned_checkout_date)}) was {data.last.status.toLowerCase()}.
              </p>
            )}
          </Card>
        </div>
      )}

      <ConfirmDialog open={!!confirm} onClose={() => setConfirm(null)} loading={busy}
        tone={confirm === 'withdraw' ? 'danger' : 'primary'}
        title={confirm === 'withdraw' ? 'Withdraw your notice?' : `Move out on ${dateFmt(chosen)}?`}
        confirmLabel={confirm === 'withdraw' ? 'Withdraw notice' : 'Send notice'}
        message={confirm === 'withdraw'
          ? 'The office is told you are staying on.'
          : short ? `This is short notice (${given} of ${required} days).` : 'The office will be told right away.'}
        onConfirm={confirm === 'withdraw' ? withdraw : give} />
    </>
  )
}
