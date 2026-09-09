import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UserPlus, BedDouble, CircleCheck, ArrowRight } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useApi, useMutation } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, FormField, Select, Input, Checkbox, StatusBadge,
  EmptyState, Avatar, InlineAlert, Skeleton,
} from '@/components/ui'
import { inr, today, dateFmt } from '@/lib/format'

/** Food charge per meal plan. Sent explicitly so the server never guesses. */
const FOOD_CHARGES = { None: 0, 'Breakfast only': 900, 'Two meals': 2400, 'All meals': 3200 }
const MEAL_PLANS = Object.keys(FOOD_CHARGES)
const BILLING_CYCLES = ['MONTHLY', 'QUARTERLY', 'HALF_YEARLY']
const CYCLE_LABEL = { MONTHLY: 'Monthly', QUARTERLY: 'Quarterly', HALF_YEARLY: 'Half-yearly' }

/**
 * Check in a resident.
 *
 * The whole move-in is one request. The bed, the agreed terms and the first
 * invoice are written by the API in a single transaction, so a failure part way
 * through cannot leave a bed occupied with nothing billed against it. The page
 * does no mutation of its own; it collects the terms and reports what came back.
 */
export default function CheckIn() {
  const { branches, apiBranchIds } = useAuth()
  const { success, error } = useToast()
  const navigate = useNavigate()

  const [residentId, setResidentId] = useState('')
  const [branchId, setBranchId] = useState('')
  const [bedId, setBedId] = useState('')
  const [joiningDate, setJoiningDate] = useState(today())
  const [rent, setRent] = useState('')
  const [deposit, setDeposit] = useState('')
  const [mealPlan, setMealPlan] = useState('Two meals')
  const [billingCycle, setBillingCycle] = useState('MONTHLY')
  const [agreement, setAgreement] = useState(false)
  const [makeInvoice, setMakeInvoice] = useState(true)

  /* Residents in the pipeline: anyone not yet living in. The API applies the
     organisation and branch filters, so this list is already safe to show. */
  const waiting = useApi(
    () => residentApi.list({ status: 'all', page_size: 100 }),
    [], { initial: null })

  const candidates = useMemo(() => {
    /* residentApi.list runs the response through unwrapList, so the shape here
       is { items, pagination } — not the raw envelope. Reading `.data` yielded
       the wrapper object itself, and calling .filter on it crashed the route. */
    const rows = waiting.data?.items || []
    return rows.filter((r) => !r.bed_id
      && !['CHECKED_OUT', 'ARCHIVED'].includes(String(r.status).toUpperCase()))
  }, [waiting.data])

  const resident = candidates.find((c) => c.id === residentId) || null

  /* Free beds, refetched whenever the branch or the chosen resident changes.
     Passing the resident id also surfaces a bed reserved for them, which is
     otherwise excluded for not being AVAILABLE. */
  const beds = useApi(
    () => residentApi.availableBeds(branchId || undefined, residentId || undefined),
    [branchId, residentId], { enabled: Boolean(branchId || residentId), initial: [] })

  const freeBeds = beds.data || []
  const bed = freeBeds.find((b) => b.id === bedId) || null

  // A bed that disappears from the list (someone else took it) must not stay selected.
  useEffect(() => {
    if (bedId && !freeBeds.some((b) => b.id === bedId)) setBedId('')
  }, [freeBeds, bedId])

  const pickBed = (b) => {
    setBedId(b.id)
    if (b.rent_amount > 0) {
      setRent(String(b.rent_amount))
      if (!deposit) setDeposit(String(b.rent_amount * 2))
    }
  }

  const foodCharge = FOOD_CHARGES[mealPlan] ?? 0
  const depositValue = Number(deposit) || Number(rent) * 2
  const invoiceTotal = Number(rent) + foodCharge + depositValue
  const ready = residentId && bedId && joiningDate && Number(rent) > 0

  const checkIn = useMutation(
    (body) => residentApi.checkIn(residentId, body),
    {
      onSuccess: (data) => {
        const where = data?.placement
          ? `Room ${data.placement.room}, bed ${data.placement.bed}`
          : 'Bed assigned'
        success(`${data?.full_name || 'Resident'} checked in`,
          data?.invoice
            ? `${where}. Invoice ${data.invoice.invoice_number} raised for ${inr(data.invoice.total)}.`
            : `${where} is now occupied.`)
        navigate(`/app/residents/${residentId}`)
      },
      onError: (err) => {
        // 409 is the expected, useful failure: the bed went while the form was
        // open, or the resident is already placed. Show the server's words.
        error('Could not complete the check-in', err.message)
        beds.reload()
      },
    })

  const submit = () => {
    if (!ready) return error('Fill in the resident, bed, date and rent before checking in.')
    checkIn.run({
      bed_id: bedId,
      joining_date: joiningDate,
      monthly_rent: Number(rent),
      security_deposit: depositValue,
      meal_plan: mealPlan,
      billing_cycle: billingCycle,
      raise_invoice: makeInvoice,
      food_charge: makeInvoice ? foodCharge : undefined,
      notes: agreement ? 'Rental agreement signed at check-in.' : undefined,
    })
  }

  if (waiting.loading && !waiting.data) {
    return (
      <Card className="p-4 space-y-2">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}
      </Card>
    )
  }
  if (waiting.error) {
    return (
      <Card className="p-4">
        <InlineAlert tone="error">
          Could not load residents. {waiting.error.message}{' '}
          <button onClick={waiting.reload} className="underline">Retry</button>
        </InlineAlert>
      </Card>
    )
  }

  return (
    <>
      <PageHeader title="Check in a resident"
        subtitle="Place someone from the pipeline into a free bed and raise their first invoice." />

      {candidates.length === 0 ? (
        <Card><EmptyState icon={UserPlus} title="Nobody is waiting for a bed"
          message="Residents who have been added but not yet placed appear here. Add one first."
          action={<Button variant="primary" onClick={() => navigate('/app/residents?new=1')}>Add a resident</Button>} /></Card>
      ) : (
        <div className="grid lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-4 items-start">
          <div className="space-y-4">
            <Card>
              <CardHeader title="Who is moving in" subtitle={`${candidates.length} in the pipeline`} />
              <div className="p-4 sm:p-5 space-y-3">
                <FormField label="Resident" required>
                  <Select value={residentId} onChange={(e) => {
                    setResidentId(e.target.value)
                    setBedId('')
                    const c = candidates.find((x) => x.id === e.target.value)
                    if (c?.branch_id) setBranchId(c.branch_id)
                    if (c?.monthly_rent > 0) setRent(String(c.monthly_rent))
                    if (c?.meal_plan) setMealPlan(c.meal_plan)
                  }}>
                    <option value="">Choose a resident…</option>
                    {candidates.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.full_name} — {c.status}{c.phone ? ` · ${c.phone}` : ''}
                      </option>
                    ))}
                  </Select>
                </FormField>

                {resident && (
                  <div className="rounded-lg border border-line bg-slate-50 p-3.5 flex items-center gap-3">
                    <Avatar name={resident.full_name} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">{resident.full_name}</p>
                      <p className="text-xs text-slate-500 truncate">
                        {[resident.occupation, resident.phone, resident.email].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    <StatusBadge status={resident.status} />
                  </div>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Which bed"
                subtitle={beds.loading ? 'Checking availability…' : `${freeBeds.length} free`}
                action={
                  <Select value={branchId} onChange={(e) => { setBranchId(e.target.value); setBedId('') }}
                    className="w-40" aria-label="Branch">
                    <option value="">All branches</option>
                    {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </Select>} />
              <div className="p-4 sm:p-5">
                {beds.loading ? (
                  <div className="space-y-2">
                    {[0, 1].map((i) => <Skeleton key={i} className="h-16" />)}
                  </div>
                ) : beds.error ? (
                  <InlineAlert tone="error">
                    Could not load beds. <button onClick={beds.reload} className="underline">Retry</button>
                  </InlineAlert>
                ) : freeBeds.length === 0 ? (
                  <EmptyState icon={BedDouble} compact title="No free beds"
                    message="Every bed here is occupied, blocked or under maintenance. Try another branch." />
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2.5 max-h-80 overflow-y-auto pr-1">
                    {freeBeds.map((b) => (
                      <button key={b.id} onClick={() => pickBed(b)}
                        className={`rounded-lg border p-3 text-left transition-colors ${
                          bedId === b.id ? 'border-brand-400 bg-brand-50 ring-1 ring-brand-300' : 'border-line hover:bg-slate-50'}`}>
                        <p className="text-sm font-semibold text-slate-900">Room {b.room_number}</p>
                        <p className="text-xs text-slate-500 truncate">
                          Bed {b.bed_code || b.bed_number}{b.room_type ? ` · ${b.room_type}` : ''}
                        </p>
                        <p className="text-xs text-slate-400 truncate">{b.building_name} · {b.branch_name}</p>
                        {b.rent_amount > 0 && (
                          <p className="text-xs font-medium text-slate-900 tnum mt-1.5">{inr(b.rent_amount)}</p>
                        )}
                        {b.reserved_for_this_resident && (
                          <StatusBadge status="Reserved" className="mt-1.5" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Terms" />
              <div className="p-4 sm:p-5 grid sm:grid-cols-2 gap-4">
                <FormField label="Joining date" required>
                  <Input type="date" value={joiningDate} onChange={(e) => setJoiningDate(e.target.value)} />
                </FormField>
                <FormField label="Billing cycle">
                  <Select value={billingCycle} onChange={(e) => setBillingCycle(e.target.value)}>
                    {BILLING_CYCLES.map((x) => <option key={x} value={x}>{CYCLE_LABEL[x]}</option>)}
                  </Select>
                </FormField>
                <FormField label="Monthly rent" required>
                  <Input inputMode="numeric" className="tnum" value={rent}
                    onChange={(e) => setRent(e.target.value)}
                    placeholder={bed ? String(bed.rent_amount) : '9000'} />
                </FormField>
                <FormField label="Security deposit">
                  <Input inputMode="numeric" className="tnum" value={deposit}
                    onChange={(e) => setDeposit(e.target.value)}
                    placeholder={rent ? String(Number(rent) * 2) : '18000'} />
                </FormField>
                <FormField label="Meal plan" className="sm:col-span-2">
                  <Select value={mealPlan} onChange={(e) => setMealPlan(e.target.value)}>
                    {MEAL_PLANS.map((x) => <option key={x}>{x}</option>)}
                  </Select>
                </FormField>
                <div className="sm:col-span-2 space-y-2.5 pt-1">
                  <Checkbox checked={agreement} onChange={(e) => setAgreement(e.target.checked)}
                    label="Rental agreement signed"
                    description="Recorded as a note. Document upload lives on the resident's KYC tab." />
                  <Checkbox checked={makeInvoice} onChange={(e) => setMakeInvoice(e.target.checked)}
                    label="Raise the first invoice"
                    description="Rent, food and deposit, in the same transaction as the check-in." />
                </div>
              </div>
            </Card>
          </div>

          {/* Sticky summary — becomes a normal card on phones */}
          <Card className="lg:sticky lg:top-20">
            <CardHeader title="Check-in summary" />
            <div className="p-5 space-y-4">
              {!ready ? (
                <p className="text-sm text-slate-500 leading-relaxed">
                  Choose a resident and a free bed, then set the rent. The summary fills in as you go.
                </p>
              ) : (
                <>
                  <dl className="space-y-2.5">
                    {[
                      ['Resident', resident?.full_name],
                      ['Branch', bed?.branch_name],
                      ['Room', `${bed?.room_number} · Bed ${bed?.bed_code || bed?.bed_number}`],
                      ['Type', bed?.room_type],
                      ['Joining', dateFmt(joiningDate, 'long')],
                      ['Meal plan', mealPlan],
                    ].filter(([, v]) => v).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-3 text-sm">
                        <dt className="text-slate-500">{k}</dt>
                        <dd className="font-medium text-slate-900 text-right">{v}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="border-t border-line pt-3 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Monthly rent</span>
                      <span className="tnum font-medium text-slate-900">{inr(rent)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">Security deposit</span>
                      <span className="tnum font-medium text-slate-900">{inr(depositValue)}</span>
                    </div>
                    {makeInvoice && (
                      <div className="flex justify-between text-sm pt-2 border-t border-line">
                        <span className="font-medium text-slate-700">First invoice</span>
                        <span className="tnum font-semibold text-slate-900">{inr(invoiceTotal)}</span>
                      </div>
                    )}
                  </div>
                  <InlineAlert tone="info" icon={CircleCheck}>
                    Bed {bed?.bed_code || bed?.bed_number} in room {bed?.room_number} will be
                    marked occupied when you confirm.
                  </InlineAlert>
                </>
              )}
              <Button variant="primary" size="lg" className="w-full" iconRight={ArrowRight}
                disabled={!ready || checkIn.busy} loading={checkIn.busy} onClick={submit}>
                {checkIn.busy ? 'Checking in…' : 'Complete check-in'}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </>
  )
}
