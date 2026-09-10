/**
 * The gate QR, on the gate desk screen.
 *
 * Check-in works in two directions and both land in the same gate log:
 *   - security scans the resident's card (the scanner on this page), or
 *   - the resident scans THIS code with their own phone. The app then also
 *     checks they are within the branch geofence, so a friend cannot scan it
 *     for them from their room.
 * The code used to be visible only under Branches → Gate setup, which a guard
 * never opens. Here it can sit on a tablet at the gate, full screen.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Maximize2, MapPin, Smartphone } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { scanApi } from '@/services/api/scanApi'
import {
  Card, CardHeader, Button, Select, QrCode, Modal, InlineAlert, Skeleton, StatusBadge,
} from '@/components/ui'

export default function GateQrCard() {
  const { activeBranchId, can } = useAuth()
  const codes = useApi(() => scanApi.gateCodes(), [])
  const [picked, setPicked] = useState('')
  const [big, setBig] = useState(false)

  const rows = codes.data || []
  const current = rows.find((b) => b.id === (picked || activeBranchId)) || rows[0]

  if (codes.error) return null
  return (
    <Card className="mb-4">
      <CardHeader title="Gate QR for residents"
        subtitle="The other direction: residents scan this with their phone to check themselves in or out."
        action={rows.length > 1 && (
          <Select value={current?.id || ''} onChange={(e) => setPicked(e.target.value)}
            className="h-9 w-44 text-xs" aria-label="Branch">
            {rows.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
        )} />
      {codes.loading && !codes.data ? <div className="p-5"><Skeleton className="h-40" /></div>
        : !current ? null : (
          <div className="p-4 sm:p-5 flex flex-col sm:flex-row gap-5 items-center sm:items-start">
            {current.gate_payload ? (
              <button onClick={() => setBig(true)} className="shrink-0 rounded-xl border border-line p-2 bg-white hover:shadow-lift transition-shadow"
                aria-label="Show the gate QR full screen">
                <QrCode value={current.gate_payload} size={148} alt={`Gate QR for ${current.name}`} />
              </button>
            ) : (
              <span className="h-[164px] w-[164px] shrink-0 rounded-xl border border-dashed border-line inline-flex items-center justify-center text-slate-300">
                <Smartphone size={30} /></span>
            )}
            <div className="min-w-0 flex-1 space-y-3 w-full">
              <div className="flex gap-2 flex-wrap">
                <StatusBadge status={current.self_checkin_enabled ? 'Self check-in on' : 'Self check-in off'}
                  tone={current.self_checkin_enabled ? 'emerald' : 'amber'} dot />
                <StatusBadge status={current.has_location ? `Within ${current.geofence_radius_m} m of the gate` : 'Location not set'}
                  tone={current.has_location ? 'slate' : 'amber'} />
              </div>
              {!current.gate_payload || !current.self_checkin_enabled || !current.has_location ? (
                <InlineAlert tone="warn" icon={MapPin} title="Not ready for residents yet">
                  Set the gate location and switch on self check-in under Branches, Gate setup.
                  Until then, scan resident cards with the scanner below.
                  {can('branches.edit') && <> <Link to="/app/branches" className="font-medium underline">Open Branches</Link></>}
                </InlineAlert>
              ) : (
                <p className="text-sm text-slate-600">
                  Keep this on a tablet or print it at the gate. Residents open <span className="font-medium">Scan</span> in
                  their app and point it here; the app checks they are really at {current.name} before recording it.
                </p>
              )}
              {current.gate_payload && (
                <Button icon={Maximize2} onClick={() => setBig(true)}>Show full screen</Button>
              )}
            </div>
          </div>
        )}

      <Modal open={big} onClose={() => setBig(false)} size="md" title={current?.name}
        subtitle="Scan with the PGDesk app to check in or out.">
        {current?.gate_payload && (
          <div className="flex flex-col items-center gap-3 py-2">
            <QrCode value={current.gate_payload} size={300} alt={`Gate QR for ${current.name}`} />
            <p className="text-xs text-slate-500 text-center">Open the app, tap Scan, point at this code.</p>
          </div>
        )}
      </Modal>
    </Card>
  )
}
