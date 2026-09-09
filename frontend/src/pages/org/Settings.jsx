import { useEffect, useState } from 'react'
import { Save, SlidersHorizontal, CreditCard } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { settingsApi } from '@/services/api/settingsApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Input, Select, Checkbox, StatCard,
  StatusBadge, InlineAlert, Skeleton, ProgressBar, Tabs,
} from '@/components/ui'
import { inr, num, dateFmt } from '@/lib/format'

const SEVERITY = { ok: 'emerald', warn: 'amber', high: 'amber', critical: 'rose' }

export default function Settings() {
  const { can, apiOrganization } = useAuth()
  const { success, error } = useToast()
  const [tab, setTab] = useState('operations')
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)

  const settings = useApi(() => settingsApi.get(), [], { enabled: can('settings.view') })
  const plan = useApi(() => subscriptionApi.mine(), [], { enabled: can('dashboard.view') })

  useEffect(() => { if (settings.data && !f) setF({ ...settings.data }) }, [settings.data])

  const set = (k) => (e) => {
    const v = e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e
    setF((x) => ({ ...x, [k]: v }))
  }

  const save = async () => {
    setBusy(true)
    try {
      await settingsApi.update({
        currency: f.currency, timezone: f.timezone,
        contact_email: f.contact_email || null, contact_phone: f.contact_phone || null,
        rent_due_day: Number(f.rent_due_day) || 5,
        late_fee_amount: Number(f.late_fee_amount) || 0,
        late_fee_after_days: Number(f.late_fee_after_days) || 0,
        invoice_prefix: f.invoice_prefix || 'INV',
        gate_duplicate_window_seconds: Number(f.gate_duplicate_window_seconds) || 0,
        visitor_approval_required: !!f.visitor_approval_required,
        gate_pass_approval_required: !!f.gate_pass_approval_required,
        food_enabled: !!f.food_enabled, laundry_enabled: !!f.laundry_enabled,
        meal_optout_cutoff_hours: Number(f.meal_optout_cutoff_hours) || 0 })
      success('Settings saved')
      settings.reload()
    } catch (err) { error('Could not save', err.message) }
    finally { setBusy(false) }
  }

  const p = plan.data

  return (
    <>
      <PageHeader title="Settings"
        subtitle="How your PG runs — billing, the gate, food and laundry."
        actions={<PermissionGuard perm="settings.manage">
          <Button variant="primary" icon={Save} loading={busy} onClick={save}
            disabled={!f}>Save changes</Button>
        </PermissionGuard>} />

      {p && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
          <StatCard label="Plan" value={p.plan || '—'} icon={CreditCard} tone="brand"
            sub={p.end_date ? `until ${dateFmt(p.end_date)}` : undefined} />
          <StatCard label="Days remaining" value={num(p.days_remaining ?? 0)}
            tone={p.days_remaining != null && p.days_remaining < 30 ? 'amber' : 'emerald'} />
          <StatCard label="Residents"
            value={`${p.usage.customers} / ${p.limits.customers}`} tone="violet"
            footer={<ProgressBar value={p.usage.customers} max={p.limits.customers || 1} />} />
          <StatCard label="Beds" value={`${p.usage.beds} / ${p.limits.beds}`} tone="slate"
            footer={<ProgressBar value={p.usage.beds} max={p.limits.beds || 1} />} />
        </div>
      )}

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'operations', label: 'Operations' },
        { value: 'billing', label: 'Billing' },
        { value: 'plan', label: 'Plan usage' },
      ]} />

      <div className="mt-4">
        {settings.error ? (
          <InlineAlert tone="error" title="Could not load settings">
            {settings.error.message}
          </InlineAlert>
        ) : !f ? <Skeleton className="h-64" /> : (
          <>
            {tab === 'operations' && (
              <div className="grid lg:grid-cols-2 gap-4">
                <Card>
                  <CardHeader title="Contact & locale" />
                  <div className="p-5 grid sm:grid-cols-2 gap-4">
                    <FormField label="Contact email">
                      <Input type="email" value={f.contact_email || ''}
                        onChange={set('contact_email')} />
                    </FormField>
                    <FormField label="Contact phone">
                      <Input value={f.contact_phone || ''} onChange={set('contact_phone')} />
                    </FormField>
                    <FormField label="Currency">
                      <Input value={f.currency} onChange={set('currency')} />
                    </FormField>
                    <FormField label="Timezone">
                      <Input value={f.timezone} onChange={set('timezone')} />
                    </FormField>
                  </div>
                </Card>

                <Card>
                  <CardHeader title="Gate, visitors and passes" />
                  <div className="p-5 space-y-4">
                    <FormField label="Ignore repeat scans within"
                      hint="Seconds. Stops one press being counted twice at the gate.">
                      <Input inputMode="numeric" className="tnum"
                        value={f.gate_duplicate_window_seconds}
                        onChange={set('gate_duplicate_window_seconds')} />
                    </FormField>
                    <Checkbox checked={!!f.visitor_approval_required}
                      onChange={set('visitor_approval_required')}
                      label="Visitors need approval before entry"
                      description="With this off, a logged visitor is approved on arrival." />
                    <Checkbox checked={!!f.gate_pass_approval_required}
                      onChange={set('gate_pass_approval_required')}
                      label="Gate passes need approval"
                      description="Security can only act on an approved pass either way." />
                  </div>
                </Card>

                <Card className="lg:col-span-2">
                  <CardHeader title="Food and laundry" />
                  <div className="p-5 grid sm:grid-cols-3 gap-4 items-start">
                    <Checkbox checked={!!f.food_enabled} onChange={set('food_enabled')}
                      label="Mess enabled"
                      description="Turns the menu and meal counts on." />
                    <Checkbox checked={!!f.laundry_enabled} onChange={set('laundry_enabled')}
                      label="Laundry enabled"
                      description="Lets residents book slots." />
                    <FormField label="Meal opt-out closes"
                      hint="Hours before the day starts.">
                      <Input inputMode="numeric" className="tnum"
                        value={f.meal_optout_cutoff_hours}
                        onChange={set('meal_optout_cutoff_hours')} />
                    </FormField>
                  </div>
                </Card>
              </div>
            )}

            {tab === 'billing' && (
              <Card className="max-w-2xl">
                <CardHeader title="Rent and invoicing"
                  subtitle="Used by the monthly rent run and late-fee sweep." />
                <div className="p-5 grid sm:grid-cols-2 gap-4">
                  <FormField label="Rent due day" hint="Day of the month, 1–28.">
                    <Input inputMode="numeric" className="tnum" value={f.rent_due_day}
                      onChange={set('rent_due_day')} />
                  </FormField>
                  <FormField label="Invoice prefix" hint="e.g. INV-00042.">
                    <Input value={f.invoice_prefix} className="uppercase"
                      onChange={set('invoice_prefix')} />
                  </FormField>
                  <FormField label="Late fee" hint="Zero disables late fees entirely.">
                    <Input inputMode="numeric" className="tnum" value={f.late_fee_amount}
                      onChange={set('late_fee_amount')} />
                  </FormField>
                  <FormField label="Charged after" hint="Days past the due date.">
                    <Input inputMode="numeric" className="tnum" value={f.late_fee_after_days}
                      onChange={set('late_fee_after_days')} />
                  </FormField>
                </div>
                <div className="px-5 pb-5">
                  <InlineAlert tone="info">
                    Late fees are applied when someone runs the sweep from the invoices
                    screen — nothing charges automatically in the background yet.
                  </InlineAlert>
                </div>
              </Card>
            )}

            {tab === 'plan' && (p ? (
              <Card>
                <CardHeader title="Usage against your plan"
                  subtitle={`${p.plan || 'No plan'} · worst: ${p.worst_severity}`} />
                <div className="p-5 grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {p.detail.filter((d) => d.limit).map((d) => (
                    <div key={d.key} className="rounded-lg border border-line p-4">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <p className="text-sm font-medium text-slate-900 capitalize">{d.plural}</p>
                        <StatusBadge status={d.severity} tone={SEVERITY[d.severity]} />
                      </div>
                      <p className="text-lg font-semibold text-slate-900 tnum">
                        {d.used}<span className="text-sm font-normal text-slate-500">
                          {' '}/ {d.limit}</span>
                      </p>
                      <ProgressBar value={d.used} max={d.limit} className="mt-2"
                        tone={SEVERITY[d.severity]} />
                    </div>
                  ))}
                </div>
                <div className="px-5 pb-5">
                  <InlineAlert tone="info">
                    Limits are enforced by the API. To change them, ask the platform
                    administrator to move you to another plan.
                  </InlineAlert>
                </div>
              </Card>
            ) : <Skeleton className="h-48" />)}
          </>
        )}
      </div>
    </>
  )
}
