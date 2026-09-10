import { useEffect, useState } from 'react'
import { MapPin, Printer, RefreshCw, Crosshair, QrCode as QrIcon } from 'lucide-react'
import QRCodeLib from 'qrcode'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import {
  Modal, Button, FormField, Input, Toggle, InlineAlert, QrCode,
} from '@/components/ui'
import { currentPosition, LocationError } from '@/lib/geo'

/**
 * One-time gate setup for a branch: where it is, how close counts as "here",
 * and the code residents scan.
 *
 * The radius is the only number here that matters and the only one an owner has
 * no intuition for, so the field explains itself rather than sitting bare. Too
 * tight and honest residents standing at the gate are refused, which produces
 * support calls nobody traces back to a number typed once during setup; too
 * loose and the fence stops meaning anything. 150 m is the default because
 * phone GPS beside a building in an Indian city is routinely 20-50 m out, and a
 * fence has to absorb that error rather than pretend it does not exist.
 */
export function GateSetup({ branch, open, onClose, onSaved }) {
  const { success, error } = useToast()

  const [lat, setLat] = useState('')
  const [lng, setLng] = useState('')
  const [radius, setRadius] = useState(150)
  const [enabled, setEnabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [locating, setLocating] = useState(false)
  const [locNote, setLocNote] = useState(null)
  const [gate, setGate] = useState(null)

  useEffect(() => {
    if (!branch) return
    setLat(branch.latitude != null ? String(branch.latitude) : '')
    setLng(branch.longitude != null ? String(branch.longitude) : '')
    setRadius(branch.geofence_radius_m ?? 150)
    setEnabled(!!branch.self_checkin_enabled)
    setGate(branch.gate_payload || null)
    setLocNote(null)
  }, [branch])

  /**
   * Fill the coordinates from the device the owner is holding.
   *
   * This is the whole reason setup is one-time and painless: standing at the
   * gate with a phone, the right answer is one tap away. Typing coordinates by
   * hand is offered as well, because the owner may be doing this from an office
   * on a desktop, where the browser's position would be the office's.
   */
  const useMyLocation = async () => {
    setLocating(true)
    setLocNote(null)
    try {
      const fix = await currentPosition()
      setLat(fix.latitude.toFixed(6))
      setLng(fix.longitude.toFixed(6))
      setLocNote(fix.accuracy != null
        ? `Filled from this device, accurate to about ${Math.round(fix.accuracy)} m. `
          + 'Stand at the gate when you do this.'
        : 'Filled from this device. Stand at the gate when you do this.')
    } catch (err) {
      error('Could not read your location',
        err instanceof LocationError ? err.message : 'Try again, or type the coordinates.')
    } finally {
      setLocating(false)
    }
  }

  const save = async () => {
    const body = {
      latitude: lat === '' ? null : Number(lat),
      longitude: lng === '' ? null : Number(lng),
      geofence_radius_m: Number(radius),
      self_checkin_enabled: enabled,
    }
    if (body.latitude !== null && Number.isNaN(body.latitude)) {
      return error('Check the latitude', 'That is not a number.')
    }
    if (body.longitude !== null && Number.isNaN(body.longitude)) {
      return error('Check the longitude', 'That is not a number.')
    }

    setBusy(true)
    try {
      const saved = await branchApi.setLocation(branch.id, body)
      setGate(saved.gate_payload || null)
      success('Gate location saved')
      onSaved?.()
    } catch (err) {
      error('Could not save', err.message)
    } finally { setBusy(false) }
  }

  const rotate = async () => {
    setBusy(true)
    try {
      const res = await branchApi.rotateGateToken(branch.id)
      setGate(res.gate_payload)
      success('New gate QR issued', 'Print it and replace the old poster.')
      onSaved?.()
    } catch (err) {
      error('Could not reissue', err.message)
    } finally { setBusy(false) }
  }

  /**
   * Print the poster.
   *
   * Rendered into a fresh window rather than with a print stylesheet on this
   * page. A modal inside an application shell brings its own layout, sidebar
   * and fonts to the printer, and taming that with CSS is far more fragile than
   * writing the one page that actually needs to exist.
   */
  const print = async () => {
    if (!gate) return
    let dataUrl
    try {
      dataUrl = await QRCodeLib.toDataURL(gate, {
        width: 1200, margin: 2, errorCorrectionLevel: 'M',
        color: { dark: '#0F172A', light: '#FFFFFF' },
      })
    } catch {
      return error('Could not prepare the poster', 'Try again.')
    }

    const w = window.open('', '_blank', 'width=800,height=1000')
    if (!w) {
      return error('The print window was blocked',
        'Allow pop-ups for this site, then try again.')
    }
    w.document.write(`<!doctype html><html><head><meta charset="utf-8">
<title>${branch.name} — gate code</title>
<style>
  @page { size: A4; margin: 18mm; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
         text-align: center; color: #0F172A; }
  h1 { font-size: 30px; margin: 0 0 4px; }
  h2 { font-size: 18px; font-weight: 500; color: #475569; margin: 0 0 28px; }
  img { width: 320px; height: 320px; image-rendering: pixelated; }
  ol { text-align: left; display: inline-block; margin: 28px auto 0;
       font-size: 15px; line-height: 1.9; color: #334155; }
  .foot { margin-top: 30px; font-size: 12px; color: #94A3B8; }
</style></head><body>
  <h1>${branch.name}</h1>
  <h2>Scan to mark your entry and exit</h2>
  <img src="${dataUrl}" alt="Gate QR code">
  <ol>
    <li>Open PGDesk and go to <strong>Gate</strong>.</li>
    <li>Wait until it shows you are at the gate.</li>
    <li>Tap the scan button and point your camera here.</li>
  </ol>
  <p class="foot">You must be within ${radius} m of this gate for the scan to count.</p>
</body></html>`)
    w.document.close()
    w.focus()
    // Give the browser a beat to decode the image; printing before it paints
    // produces a page with an empty box where the code should be.
    setTimeout(() => w.print(), 400)
  }

  const positioned = lat !== '' && lng !== ''

  return (
    <Modal open={open} onClose={onClose} size="lg"
      title={`Gate & self check-in — ${branch?.name || ''}`}
      footer={<><Button onClick={onClose}>Close</Button>
        <Button variant="primary" loading={busy} onClick={save}>Save</Button></>}>

      <div className="grid md:grid-cols-2 gap-5">
        {/* ------------------------------------------------------ location */}
        <div className="space-y-4">
          <div>
            <p className="text-sm font-semibold text-slate-900 mb-1">Where the gate is</p>
            <p className="text-xs text-slate-500">
              Set this once. Residents can only check themselves in when their
              phone is inside the circle you draw here.
            </p>
          </div>

          <Button icon={Crosshair} onClick={useMyLocation} loading={locating}
            className="w-full">
            Use my current location
          </Button>
          {locNote && <InlineAlert tone="info">{locNote}</InlineAlert>}

          <div className="grid grid-cols-2 gap-3">
            <FormField label="Latitude">
              <Input value={lat} onChange={(e) => setLat(e.target.value)}
                inputMode="decimal" placeholder="12.934533" className="font-mono" />
            </FormField>
            <FormField label="Longitude">
              <Input value={lng} onChange={(e) => setLng(e.target.value)}
                inputMode="decimal" placeholder="77.626579" className="font-mono" />
            </FormField>
          </div>

          <FormField label="How close must they be?"
            hint="Metres from the gate. 150 is a good starting point — phone GPS
                  near a building is often 20–50 m out, and too small a number
                  refuses residents who really are standing there.">
            <Input type="number" min={10} max={5000} value={radius}
              onChange={(e) => setRadius(e.target.value)} className="tnum" />
          </FormField>

          <div className="rounded-lg border border-line px-3">
            <Toggle checked={enabled} onChange={setEnabled} disabled={!positioned}
              label="Let residents check themselves in"
              description={positioned
                ? 'Security can still scan resident cards as usual.'
                : 'Set the location first.'} />
          </div>
        </div>

        {/* ---------------------------------------------------- the QR code */}
        <div className="space-y-4">
          <div>
            <p className="text-sm font-semibold text-slate-900 mb-1">The gate code</p>
            <p className="text-xs text-slate-500">
              Print this and fix it at the gate. Residents scan it; it is not a
              resident card and cannot identify anyone.
            </p>
          </div>

          {gate ? (
            <>
              <div className="flex justify-center p-4 rounded-xl border border-line bg-white">
                <QrCode value={gate} size={190} alt={`Gate QR for ${branch?.name}`} />
              </div>
              <div className="flex gap-2">
                <Button icon={Printer} className="flex-1" onClick={print}>Print poster</Button>
                <Button icon={RefreshCw} onClick={rotate} loading={busy}>Reissue</Button>
              </div>
              <InlineAlert tone="warn" title="Reissuing invalidates the old poster">
                Do it if you think a photo of the code is being passed around.
                Every printed copy stops working straight away, so replace them
                all at the same time.
              </InlineAlert>
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-line p-8 text-center">
              <QrIcon size={26} className="mx-auto text-slate-300 mb-2" />
              <p className="text-sm text-slate-600">No gate code yet</p>
              <p className="text-2xs text-slate-500 mt-1">
                Set the location and switch self check-in on. A code is issued
                automatically when you save.
              </p>
            </div>
          )}
        </div>
      </div>

      <InlineAlert tone="info" className="mt-5" title="What this does and does not prove">
        A resident has to scan the code at the gate <em>and</em> be inside the
        circle. That stops a code being photographed and shared with someone
        sitting at home. It does not stop a determined person using a
        fake-location app, so every check-in stores the position it was made
        from — an account whose entries come from scattered impossible places
        shows up in the gate log.
      </InlineAlert>
    </Modal>
  )
}
