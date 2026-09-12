/**
 * Asking the owner to show their free beds to people looking for a PG.
 *
 * Public listing has existed for a while, but only as a switch inside
 * Branches -> Listing, off by default. Nobody finds a switch they do not know
 * about, so the dashboard now asks - once there are free beds to show - and the
 * whole setup is one sheet: which branches, which phone number, and whether
 * the branch is on the map (without a position it cannot appear in a "near me"
 * search, which is how most people look).
 *
 * Off stays the default. Nothing is published until the owner presses the
 * button, and "Not now" hides the prompt for a week rather than forever.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Megaphone, MapPin, CheckCircle2, Crosshair, Inbox } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/lib/useApi'
import { branchApi } from '@/services/api/branchApi'
import { currentPosition } from '@/lib/geo'
import {
  Card, Button, Modal, Toggle, Input, FormField, InlineAlert, StatusBadge,
} from '@/components/ui'

const SNOOZE_DAYS = 7
const snoozeKey = (orgId) => `pgguru.shareBeds.snoozed.${orgId || 'org'}`

function snoozedRecently(orgId) {
  try {
    const at = Number(window.localStorage.getItem(snoozeKey(orgId)) || 0)
    return at > 0 && Date.now() - at < SNOOZE_DAYS * 24 * 60 * 60 * 1000
  } catch { return false }
}

export function ShareBedsCard({ byBranch = [] }) {
  const { can, org } = useAuth()
  const allowed = can('branches.edit') && can('branches.view')
  const branches = useApi(() => branchApi.list({ page_size: 200 }), [], { enabled: allowed })
  const [snoozed, setSnoozed] = useState(() => snoozedRecently(org?.id))
  const [open, setOpen] = useState(false)

  const freeById = useMemo(
    () => Object.fromEntries(byBranch.map((b) => [b.id, Number(b.available) || 0])), [byBranch])

  if (!allowed || !branches.data) return null
  const active = (branches.data.items || []).filter((b) => b.status === 'ACTIVE')
  const withFree = active.filter((b) => (freeById[b.id] || 0) > 0)
  const freeTotal = withFree.reduce((sum, b) => sum + freeById[b.id], 0)
  if (freeTotal === 0) return null

  const hidden = withFree.filter((b) => !b.listed_publicly)
  const shownFree = withFree.filter((b) => b.listed_publicly)
    .reduce((sum, b) => sum + freeById[b.id], 0)

  const sheet = (
    <ShareBedsModal open={open} onClose={() => setOpen(false)} branches={active}
      freeById={freeById} onSaved={() => { setOpen(false); branches.reload() }} />
  )

  if (hidden.length === 0) {
    return (
      <>
        <Card className="mb-4 px-4 py-3 flex flex-wrap items-center gap-3">
          <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
          <p className="text-sm text-slate-700 flex-1 min-w-[12rem]">
            {shownFree} free bed{shownFree === 1 ? ' is' : 's are'} visible to people looking for a PG nearby.
          </p>
          <div className="flex gap-2">
            <Link to="/app/enquiries"><Button size="sm" icon={Inbox}>Enquiries</Button></Link>
            <Button size="sm" onClick={() => setOpen(true)}>Manage</Button>
          </div>
        </Card>
        {sheet}
      </>
    )
  }

  if (snoozed) return null

  const snooze = () => {
    try { window.localStorage.setItem(snoozeKey(org?.id), String(Date.now())) } catch { /* ignore */ }
    setSnoozed(true)
  }

  return (
    <>
      <Card className="mb-4 overflow-hidden border-brand-200">
        <div className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4 bg-brand-50/60">
          <span className="h-11 w-11 rounded-xl bg-brand-700 text-white inline-flex items-center justify-center shrink-0">
            <Megaphone size={20} />
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-[15px] font-semibold text-slate-900">
              Fill your {freeTotal} free bed{freeTotal === 1 ? '' : 's'} faster
            </p>
            <p className="text-sm text-slate-600 mt-0.5">
              Show them to people searching for a PG near you. Enquiries come straight to
              your Enquiries inbox, with no broker and no fee. Resident details are never shown.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button variant="primary" onClick={() => setOpen(true)}>Show my free beds</Button>
            <Button variant="ghost" onClick={snooze}>Not now</Button>
          </div>
        </div>
      </Card>
      {sheet}
    </>
  )
}

function ShareBedsModal({ open, onClose, branches, freeById, onSaved }) {
  const { success, error } = useToast()
  const [rows, setRows] = useState({})
  const [busy, setBusy] = useState(false)
  const [locating, setLocating] = useState(null)

  useEffect(() => {
    if (!open) return
    setRows(Object.fromEntries(branches.map((b) => [b.id, {
      on: !!b.listed_publicly || (freeById[b.id] || 0) > 0,
      phone: b.contact_phone_public || b.contact_number || '',
      lat: b.latitude, lng: b.longitude,
    }])))
  }, [open, branches, freeById])

  const set = (id, patch) => setRows((x) => ({ ...x, [id]: { ...x[id], ...patch } }))

  const locate = async (b) => {
    setLocating(b.id)
    try {
      const pos = await currentPosition()
      await branchApi.setLocation(b.id, { latitude: pos.latitude, longitude: pos.longitude })
      set(b.id, { lat: pos.latitude, lng: pos.longitude })
      success(`${b.name} is on the map`)
    } catch (err) {
      error('Could not set the location', err.message)
    } finally { setLocating(null) }
  }

  const save = async () => {
    setBusy(true)
    let changed = 0
    try {
      for (const b of branches) {
        const row = rows[b.id]
        if (!row) continue
        const on = row.on && !!(b.city || b.address)
        if (!on && !b.listed_publicly) continue
        const phone = (row.phone || '').trim()
        if (on === !!b.listed_publicly && phone === (b.contact_phone_public || '')) continue
        await branchApi.setListing(b.id, { listed_publicly: on, contact_phone_public: phone || null })
        changed += 1
      }
      success(changed ? 'Saved. People searching nearby can now see your free beds.'
        : 'Nothing changed')
      onSaved?.()
    } catch (err) {
      error('Could not save', err.message)
    } finally { setBusy(false) }
  }

  return (
    <Modal open={open} onClose={onClose} size="md" title="Show free beds to people looking for a PG"
      subtitle="Choose the branches to show. You can switch this off any time."
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>
      <InlineAlert tone="info" title="What people will see">
        Your PG name, area, which kinds of room have a free bed and their starting rent,
        amenities, and the phone number below. Free beds show as “a few beds”, never an
        exact number. Resident details are never shown.
      </InlineAlert>

      <div className="mt-4 divide-y divide-line rounded-lg border border-line">
        {branches.map((b) => {
          const row = rows[b.id] || {}
          const free = freeById[b.id] || 0
          const hasAddress = !!(b.city || b.address)
          const onMap = row.lat != null && row.lng != null
          return (
            <div key={b.id} className="px-4 py-3 space-y-3">
              <Toggle checked={!!row.on && hasAddress} disabled={!hasAddress}
                onChange={(v) => set(b.id, { on: v })} ariaLabel={`Show ${b.name}`}
                label={<span className="flex items-center gap-2 flex-wrap">{b.name}
                  <StatusBadge status={free ? `${free} free` : 'Full'} tone={free ? 'emerald' : 'slate'} />
                </span>}
                description={!hasAddress ? 'Add an address or city to this branch first (Branches, then Edit).'
                  : b.listed_publicly ? 'Visible now.' : 'Not visible yet.'} />
              {row.on && hasAddress && (
                <div className="grid sm:grid-cols-2 gap-3">
                  <FormField label="Phone for enquiries" hint="Shown on your listing. A desk number is best.">
                    <Input value={row.phone || ''} inputMode="tel"
                      onChange={(e) => set(b.id, { phone: e.target.value })} />
                  </FormField>
                  <div>
                    <p className="text-[13px] font-medium text-slate-700 mb-1.5">On the map</p>
                    {onMap ? (
                      <p className="h-10 text-sm text-emerald-700 inline-flex items-center gap-1.5">
                        <MapPin size={14} /> Location set
                      </p>
                    ) : (
                      <>
                        <Button size="sm" icon={Crosshair} loading={locating === b.id}
                          onClick={() => locate(b)}>Use my current location</Button>
                        <p className="text-xs text-amber-700 mt-1.5">
                          Without it, “near me” searches will not show this branch. Tap
                          this while standing at the PG.
                        </p>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <p className="text-xs text-slate-500 mt-3">
        Headline, description and amenities are under Branches, then Listing.
      </p>
    </Modal>
  )
}
