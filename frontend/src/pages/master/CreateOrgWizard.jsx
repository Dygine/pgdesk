import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ArrowRight, Building2, Check, Copy, Download, KeyRound, User, CreditCard,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { organizationApi } from '@/services/api/organizationApi'
import { subscriptionApi } from '@/services/api/subscriptionApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Input, Select, Textarea, StatusBadge,
  InlineAlert, Skeleton,
} from '@/components/ui'
import { inr, dateFmt, today } from '@/lib/format'

const STEPS = [
  { key: 'pg', label: 'PG details', icon: Building2 },
  { key: 'owner', label: 'Owner', icon: User },
  { key: 'plan', label: 'Plan', icon: CreditCard },
  { key: 'done', label: 'Credentials', icon: KeyRound },
]

const addDays = (n) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d.toISOString().slice(0, 10)
}

/**
 * One POST creates the organisation, its subscription, the Owner role and the
 * owner account. The temporary password comes back once and is shown on the
 * last step — it exists nowhere else in readable form.
 */
export default function CreateOrgWizard() {
  const navigate = useNavigate()
  const { success, error } = useToast()
  const plans = useApi(() => subscriptionApi.plans(), [])

  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const [errs, setErrs] = useState({})
  const [f, setF] = useState({
    name: '', legal_name: '', pg_type: 'Co-living', gender: 'Unisex',
    owner_name: '', owner_email: '', owner_phone: '',
    address: '', city: 'Bengaluru', state: 'Karnataka', pincode: '', gstin: '',
    notes: '', plan_code: '', status: 'TRIAL',
    subscription_start: today(), subscription_end: addDays(30),
  })

  const set = (k) => (e) => {
    setF((x) => ({ ...x, [k]: e.target.value }))
    setErrs((x) => ({ ...x, [k]: undefined }))
  }

  const plan = (plans.data || []).find((p) => p.code === f.plan_code)

  const validate = () => {
    const e = {}
    if (step === 0) {
      if (f.name.trim().length < 2) e.name = 'Give the PG a name.'
    }
    if (step === 1) {
      if (f.owner_name.trim().length < 2) e.owner_name = 'Enter the owner’s name.'
      if (!/^\S+@\S+\.\S+$/.test(f.owner_email)) e.owner_email = 'Enter a valid email address.'
    }
    if (step === 2) {
      if (!f.plan_code) e.plan_code = 'Choose a plan.'
      if (f.subscription_end <= f.subscription_start)
        e.subscription_end = 'The end date must be after the start date.'
    }
    setErrs(e)
    return Object.keys(e).length === 0
  }

  const next = () => { if (validate()) setStep((s) => s + 1) }

  const submit = async () => {
    if (!validate()) return
    setBusy(true)
    try {
      const result = await organizationApi.create(f)
      setCreated(result)
      setStep(3)
      success(`${result.organization.name} created`,
        'Share the temporary password with the owner securely.')
    } catch (err) {
      error('Could not create the organisation', err.message)
      const fields = err.fieldErrors || {}
      if (Object.keys(fields).length) setErrs(fields)
    } finally { setBusy(false) }
  }

  const copy = (text, label) => {
    navigator.clipboard?.writeText(text)
    success(`${label} copied`)
  }

  const download = () => {
    const c = created.owner
    const body = [
      'PGDesk — owner credentials', '',
      `Organisation : ${created.organization.name}`,
      `Owner        : ${c.name}`,
      `Email        : ${c.email}`,
      `Password     : ${c.temporary_password}`, '',
      'This is a temporary password. The owner is required to change it on first sign-in.',
      'Send it over a channel the recipient controls; do not email it alongside the address.',
    ].join('\n')
    const url = URL.createObjectURL(new Blob([body], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `pgdesk-owner-${created.organization.slug}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <PageHeader
        breadcrumb={<><Link to="/master/organizations" className="hover:text-slate-800">Organisations</Link>
          <span>/</span><span className="text-slate-700">New</span></>}
        title="Create a PG"
        subtitle="Sets up the organisation, its subscription, the owner role and the owner account." />

      {/* Steps — horizontal on desktop, compact on a phone */}
      <div className="flex items-center gap-2 sm:gap-4 mb-5 overflow-x-auto pb-1">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center gap-2 sm:gap-4 shrink-0">
            <div className={`flex items-center gap-2 ${i <= step ? 'text-brand-800' : 'text-slate-400'}`}>
              <span className={`h-8 w-8 rounded-lg inline-flex items-center justify-center shrink-0 ${
                i < step ? 'bg-emerald-50 text-emerald-600'
                  : i === step ? 'bg-brand-700 text-white' : 'bg-slate-100 text-slate-400'}`}>
                {i < step ? <Check size={16} /> : <s.icon size={16} />}
              </span>
              <span className="text-sm font-medium whitespace-nowrap">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && <span className="h-px w-6 sm:w-10 bg-line" />}
          </div>
        ))}
      </div>

      <Card className="max-w-3xl">
        {step === 0 && (
          <>
            <CardHeader title="PG details" subtitle="What the property is and where it is." />
            <div className="p-5 grid sm:grid-cols-2 gap-4">
              <FormField label="PG name" required error={errs.name} className="sm:col-span-2">
                <Input value={f.name} onChange={set('name')} error={errs.name}
                  placeholder="Sunrise Living PG" />
              </FormField>
              <FormField label="Registered name">
                <Input value={f.legal_name} onChange={set('legal_name')}
                  placeholder="Sunrise Living Accommodations LLP" />
              </FormField>
              <FormField label="GSTIN">
                <Input value={f.gstin} onChange={set('gstin')} placeholder="29ABCDE1234F1Z5" />
              </FormField>
              <FormField label="Type">
                <Select value={f.pg_type} onChange={set('pg_type')}>
                  {['Co-living', 'Gents PG', 'Ladies PG', 'Hostel', 'Service apartment']
                    .map((x) => <option key={x}>{x}</option>)}
                </Select>
              </FormField>
              <FormField label="Accepts">
                <Select value={f.gender} onChange={set('gender')}>
                  {['Unisex', 'Male', 'Female'].map((x) => <option key={x}>{x}</option>)}
                </Select>
              </FormField>
              <FormField label="Address" className="sm:col-span-2">
                <Textarea rows={2} value={f.address} onChange={set('address')} />
              </FormField>
              <FormField label="City"><Input value={f.city} onChange={set('city')} /></FormField>
              <FormField label="State"><Input value={f.state} onChange={set('state')} /></FormField>
              <FormField label="Pincode"><Input value={f.pincode} onChange={set('pincode')} /></FormField>
              <FormField label="Notes" className="sm:col-span-2"
                hint="Internal — visible to platform administrators only.">
                <Textarea rows={2} value={f.notes} onChange={set('notes')} />
              </FormField>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <CardHeader title="Owner account"
              subtitle="They receive full control of the organisation and every branch." />
            <div className="p-5 grid sm:grid-cols-2 gap-4">
              <FormField label="Owner name" required error={errs.owner_name} className="sm:col-span-2">
                <Input value={f.owner_name} onChange={set('owner_name')} error={errs.owner_name}
                  placeholder="Rahul Sharma" />
              </FormField>
              <FormField label="Email" required error={errs.owner_email}
                hint="Becomes their sign-in address.">
                <Input type="email" value={f.owner_email} onChange={set('owner_email')}
                  error={errs.owner_email} />
              </FormField>
              <FormField label="Phone">
                <Input value={f.owner_phone} onChange={set('owner_phone')}
                  placeholder="+91 98450 12233" />
              </FormField>
              <InlineAlert tone="info" className="sm:col-span-2" icon={KeyRound}>
                A temporary password is generated when you finish. The owner is required to
                change it the first time they sign in, so the password you see is never the
                one they end up using.
              </InlineAlert>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <CardHeader title="Subscription" subtitle="Plan limits are enforced by the API." />
            <div className="p-5 space-y-4">
              {plans.loading ? <Skeleton className="h-24" /> : (
                <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {(plans.data || []).map((p) => (
                    <button key={p.code} type="button"
                      onClick={() => { setF((x) => ({ ...x, plan_code: p.code })); setErrs({}) }}
                      className={`rounded-lg border p-4 text-left transition-colors ${
                        f.plan_code === p.code
                          ? 'border-brand-400 bg-brand-50 ring-1 ring-brand-300'
                          : 'border-line hover:bg-slate-50'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-slate-900">{p.name}</p>
                        {f.plan_code === p.code && <Check size={15} className="text-brand-700" />}
                      </div>
                      <p className="text-base font-semibold text-slate-900 tnum mt-1">
                        {inr(p.price)}<span className="text-xs font-normal text-slate-500">/mo</span>
                      </p>
                      <dl className="mt-2 space-y-0.5">
                        {[['Branches', p.limits.branches], ['Rooms', p.limits.rooms],
                          ['Beds', p.limits.beds], ['Users', p.limits.users]].map(([k, v]) => (
                          <div key={k} className="flex justify-between text-2xs">
                            <dt className="text-slate-500">{k}</dt>
                            <dd className="tnum text-slate-700">{v}</dd>
                          </div>
                        ))}
                      </dl>
                    </button>
                  ))}
                </div>
              )}
              {errs.plan_code && <p className="text-xs text-rose-600">{errs.plan_code}</p>}

              <div className="grid sm:grid-cols-3 gap-4 pt-2">
                <FormField label="Status">
                  <Select value={f.status} onChange={set('status')}>
                    {['TRIAL', 'ACTIVE'].map((x) => <option key={x}>{x}</option>)}
                  </Select>
                </FormField>
                <FormField label="Starts">
                  <Input type="date" value={f.subscription_start} onChange={set('subscription_start')} />
                </FormField>
                <FormField label="Ends" error={errs.subscription_end}>
                  <Input type="date" value={f.subscription_end} onChange={set('subscription_end')}
                    error={errs.subscription_end} />
                </FormField>
              </div>
            </div>
          </>
        )}

        {step === 3 && created && (
          <>
            <CardHeader title="Owner credentials"
              subtitle="Shown once. Share them over a channel the owner controls." />
            <div className="p-5 space-y-4">
              <div className="rounded-lg border border-line bg-slate-50 p-4 space-y-2.5">
                {[['Organisation', created.organization.name],
                  ['Owner', created.owner.name],
                  ['Email', created.owner.email],
                  ['Temporary password', created.owner.temporary_password]].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-3">
                    <span className="text-xs text-slate-500">{k}</span>
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-sm text-slate-900 truncate">{v}</span>
                      <button type="button" onClick={() => copy(v, k)}
                        className="text-slate-400 hover:text-slate-700 shrink-0"
                        aria-label={`Copy ${k}`}><Copy size={14} /></button>
                    </span>
                  </div>
                ))}
              </div>

              <InlineAlert tone="warn" title="This password is not recoverable">
                It is stored only as an Argon2 hash. If it is lost, issue a new one from the
                organisation page rather than trying to look it up.
              </InlineAlert>

              <div className="flex flex-col sm:flex-row gap-2">
                <Button icon={Download} className="flex-1" onClick={download}>Download</Button>
                <Button variant="primary" className="flex-1"
                  onClick={() => navigate(`/master/organizations/${created.organization.id}`)}>
                  Open the organisation
                </Button>
              </div>
            </div>
          </>
        )}

        {step < 3 && (
          <div className="px-5 py-4 border-t border-line flex items-center justify-between gap-3">
            <Button icon={ArrowLeft} disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
              Back
            </Button>
            {step < 2 ? (
              <Button variant="primary" iconRight={ArrowRight} onClick={next}>Continue</Button>
            ) : (
              <Button variant="primary" loading={busy} onClick={submit}>Create the PG</Button>
            )}
          </div>
        )}
      </Card>
    </>
  )
}
