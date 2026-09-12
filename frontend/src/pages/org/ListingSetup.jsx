import { useEffect, useState } from 'react'
import { branchApi } from '@/services/api/branchApi'
import { BranchPhotos } from '@/components/domain/BranchPhotos'
import { useToast } from '@/context/ToastContext'
import {
  Modal, Button, FormField, Input, Select, Textarea, Toggle, InlineAlert,
} from '@/components/ui'

/** Ticked on and off rather than typed, so the values stay consistent enough to filter on. */
const AMENITIES = [
  'WiFi', 'Meals', 'Laundry', 'AC', 'Power backup', 'Housekeeping',
  'Parking', 'CCTV', 'Attached bathroom', 'Gym', 'Refrigerator', 'Hot water',
]

/**
 * Publishing a branch to the public search.
 *
 * The alert at the top is not decoration. Listing makes an address, a price and
 * a vacancy signal readable by anyone on the internet, including competitors,
 * and an owner who discovers that after the fact would be right to be angry. So
 * the screen says exactly what becomes public before the switch is reachable,
 * and the switch is off until someone deliberately turns it on.
 */
export function ListingSetup({ branch, open, onClose, onSaved }) {
  const { success, error } = useToast()
  const [f, setF] = useState({
    listed_publicly: false, listing_headline: '', listing_description: '',
    starting_rent: '', gender_preference: 'ANY', contact_phone_public: '',
  })
  const [amenities, setAmenities] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!branch) return
    setF({
      listed_publicly: !!branch.listed_publicly,
      listing_headline: branch.listing_headline || '',
      listing_description: branch.listing_description || '',
      starting_rent: branch.starting_rent ?? '',
      gender_preference: branch.gender_preference || 'ANY',
      contact_phone_public: branch.contact_phone_public || branch.contact_number || '',
    })
    setAmenities(branch.amenities || [])
  }, [branch])

  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e?.target ? e.target.value : e }))

  const toggleAmenity = (a) =>
    setAmenities((list) => list.includes(a) ? list.filter((x) => x !== a) : [...list, a])

  const save = async () => {
    setBusy(true)
    try {
      const res = await branchApi.setListing(branch.id, {
        listed_publicly: f.listed_publicly,
        listing_headline: f.listing_headline || null,
        listing_description: f.listing_description || null,
        starting_rent: f.starting_rent === '' ? null : Number(f.starting_rent),
        gender_preference: f.gender_preference,
        amenities,
        contact_phone_public: f.contact_phone_public || null,
      })
      success(res.listed_publicly ? 'Branch is now listed' : 'Branch is no longer listed')
      onSaved?.()
      onClose?.()
    } catch (err) {
      error('Could not save the listing', err.message)
    } finally { setBusy(false) }
  }

  const canList = !!(branch?.city || branch?.address)

  return (
    <Modal open={open} onClose={onClose} size="lg"
      title={`Public listing — ${branch?.name || ''}`}
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} onClick={save}>Save listing</Button></>}>

      <InlineAlert tone={f.listed_publicly ? 'warn' : 'info'}
        title={f.listed_publicly ? 'This branch is public' : 'What becomes public'}>
        Anyone searching PGuru sees the name, area, starting rent, amenities,
        which kinds of room have a free bed and the phone number you enter here.
        Availability shows only as a rough
        band — “a few beds”, never an exact count — so nobody can track your
        occupancy. Resident details are never published.
      </InlineAlert>

      {!canList && (
        <InlineAlert tone="error" className="mt-3" title="Add an address first">
          This branch has no city or address, so nobody searching would find it.
          Add one under Edit before listing.
        </InlineAlert>
      )}

      <div className="rounded-lg border border-line px-3 mt-4">
        <Toggle checked={f.listed_publicly} disabled={!canList}
          onChange={(v) => setF((x) => ({ ...x, listed_publicly: v }))}
          label="List this branch publicly"
          description={canList
            ? 'People looking for a PG can find it and send enquiries.'
            : 'Add a city or address first.'} />
      </div>

      <div className="grid sm:grid-cols-2 gap-4 mt-5">
        <FormField label="Headline" className="sm:col-span-2"
          hint="One line. This is the first thing a seeker reads.">
          <Input value={f.listing_headline} onChange={set('listing_headline')}
            maxLength={160} placeholder="Quiet PG for working professionals, 5 min from the metro" />
        </FormField>

        <FormField label="Description" className="sm:col-span-2">
          <Textarea rows={3} value={f.listing_description}
            onChange={set('listing_description')} maxLength={2000}
            placeholder="Meals included, weekly laundry, walking distance to the tech park." />
        </FormField>

        <FormField label="Starting rent"
          hint="The lowest monthly rent you would quote. Leave blank for “on request”.">
          <Input type="number" inputMode="numeric" value={f.starting_rent}
            onChange={set('starting_rent')} className="tnum" placeholder="9500" />
        </FormField>

        <FormField label="Open to">
          <Select value={f.gender_preference} onChange={set('gender_preference')}>
            <option value="ANY">Anyone</option>
            <option value="MALE">Men only</option>
            <option value="FEMALE">Women only</option>
          </Select>
        </FormField>

        <FormField label="Public phone number" className="sm:col-span-2"
          hint="Shown on the listing so seekers can call. Use a desk number, not a personal one.">
          <Input value={f.contact_phone_public} onChange={set('contact_phone_public')}
            inputMode="tel" />
        </FormField>
      </div>

      <div className="mt-6">
        <p className="text-sm font-medium text-slate-800">Photos</p>
        <p className="text-xs text-slate-500 mb-2.5">
          A listing with photos gets opened far more often than one without. Take
          them on your phone - they are shrunk to under 5 KB here before anything
          is uploaded, so this works on any connection.
        </p>
        <BranchPhotos branchId={branch?.id} />
      </div>

      <div className="mt-6">
        <p className="text-sm font-medium text-slate-800 mb-2">Amenities</p>
        <div className="flex flex-wrap gap-2">
          {AMENITIES.map((a) => {
            const on = amenities.includes(a)
            return (
              <button key={a} type="button" onClick={() => toggleAmenity(a)}
                className={`text-xs rounded-full px-3 py-1.5 border transition-colors ${
                  on ? 'bg-brand-700 border-brand-700 text-white'
                     : 'bg-white border-line text-slate-600 hover:border-brand-400'}`}>
                {a}
              </button>
            )
          })}
        </div>
      </div>
    </Modal>
  )
}
