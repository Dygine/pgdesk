import { useState } from 'react'
import { Building, Layers3, DoorOpen, BedDouble, ChevronRight } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { propertyApi } from '@/services/api/propertyApi'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, StatCard, StatusBadge, EmptyState, Skeleton, InlineAlert, ProgressBar,
} from '@/components/ui'
import { inr, num } from '@/lib/format'

const BED_STYLE = {
  OCCUPIED: 'bg-brand-100 text-brand-800 border-brand-200',
  AVAILABLE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  RESERVED: 'bg-amber-50 text-amber-700 border-amber-200',
  MAINTENANCE: 'bg-rose-50 text-rose-700 border-rose-200',
  BLOCKED: 'bg-slate-100 text-slate-500 border-slate-200',
}

/** Branch → building → floor → room → bed, drilled down one level at a time. */
export default function Blueprint() {
  const { activeBranchId } = useAuth()
  const blueprint = useApi(() => propertyApi.blueprint(activeBranchId), [activeBranchId])
  const [open, setOpen] = useState({})

  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }))
  const branches = blueprint.data || []

  const totals = branches.reduce((a, b) => {
    const rooms = b.buildings.flatMap((x) => x.floors).flatMap((x) => x.rooms)
    const beds = rooms.flatMap((r) => r.beds)
    return {
      buildings: a.buildings + b.buildings.length,
      floors: a.floors + b.buildings.reduce((n, x) => n + x.floors.length, 0),
      rooms: a.rooms + rooms.length,
      beds: a.beds + beds.length,
      occupied: a.occupied + beds.filter((x) => x.status === 'OCCUPIED').length,
    }
  }, { buildings: 0, floors: 0, rooms: 0, beds: 0, occupied: 0 })

  return (
    <>
      <PageHeader title="Property blueprint"
        subtitle="The full hierarchy, with live occupancy at every level." />

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-4">
        <StatCard label="Branches" value={num(branches.length)} icon={Building} tone="brand" />
        <StatCard label="Buildings" value={num(totals.buildings)} tone="violet" />
        <StatCard label="Floors" value={num(totals.floors)} icon={Layers3} tone="blue" />
        <StatCard label="Rooms" value={num(totals.rooms)} icon={DoorOpen} tone="slate" />
        <StatCard label="Occupancy"
          value={totals.beds ? `${Math.round(totals.occupied / totals.beds * 100)}%` : '—'}
          icon={BedDouble} tone="emerald" sub={`${totals.occupied}/${totals.beds} beds`} />
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        {Object.entries(BED_STYLE).map(([status, cls]) => (
          <span key={status} className="inline-flex items-center gap-1.5 text-xs text-slate-600">
            <span className={`h-3.5 w-3.5 rounded border ${cls}`} />{status.toLowerCase()}
          </span>
        ))}
      </div>

      {blueprint.error ? (
        <InlineAlert tone="error" title="Could not load the blueprint">
          {blueprint.error.message}
        </InlineAlert>
      ) : blueprint.loading && !blueprint.data ? (
        <Skeleton className="h-72" />
      ) : branches.length === 0 ? (
        <Card><EmptyState icon={Building} title="Nothing to show yet"
          message="Create a branch, a building, a floor and a room — the blueprint fills itself in." /></Card>
      ) : (
        <div className="space-y-4">
          {branches.map((branch) => (
            <Card key={branch.id}>
              <CardHeader title={branch.name}
                subtitle={`${branch.code} · ${branch.occupancy.total} beds · ${branch.occupancy.rate}% occupied`}
                action={<StatusBadge status={branch.status} dot />} />

              {branch.buildings.length === 0 ? (
                <EmptyState compact title="No buildings in this branch" />
              ) : (
                <div className="divide-y divide-line">
                  {branch.buildings.map((building) => (
                    <div key={building.id} className="p-4 sm:p-5">
                      <button onClick={() => toggle(building.id)}
                        className="w-full flex items-center gap-2.5 text-left mb-3">
                        <ChevronRight size={16}
                          className={`text-slate-400 transition-transform shrink-0 ${
                            open[building.id] === false ? '' : 'rotate-90'}`} />
                        <span className="h-8 w-8 rounded-lg bg-brand-50 text-brand-700 inline-flex items-center justify-center shrink-0">
                          <Building size={16} />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-slate-900 truncate">
                            {building.name}
                          </span>
                          <span className="block text-2xs text-slate-500">
                            {building.floors.length} floors ·{' '}
                            {building.floors.reduce((n, fl) => n + fl.rooms.length, 0)} rooms
                          </span>
                        </span>
                      </button>

                      {open[building.id] !== false && (
                        <div className="space-y-4 sm:pl-11">
                          {building.floors.map((floor) => (
                            <div key={floor.id}>
                              <div className="flex items-center gap-2 mb-2">
                                <Layers3 size={14} className="text-slate-400" />
                                <p className="text-xs font-medium text-slate-700">{floor.name}</p>
                                <span className="text-2xs text-slate-400 tnum">
                                  {floor.rooms.length} rooms
                                </span>
                              </div>

                              {floor.rooms.length === 0 ? (
                                <p className="text-xs text-slate-400 pl-5">No rooms on this floor.</p>
                              ) : (
                                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2.5 pl-5">
                                  {floor.rooms.map((room) => (
                                    <div key={room.id} className="rounded-lg border border-line p-3">
                                      <div className="flex items-start justify-between gap-2">
                                        <div className="min-w-0">
                                          <p className="text-sm font-medium text-slate-900">
                                            Room {room.room_number}
                                          </p>
                                          <p className="text-2xs text-slate-500 truncate">
                                            {room.room_type}
                                          </p>
                                        </div>
                                        {room.has_ac && <StatusBadge status="AC" tone="blue" />}
                                      </div>

                                      <div className="flex gap-1 mt-2 flex-wrap">
                                        {room.beds.map((bed) => (
                                          <span key={bed.id}
                                            title={`Bed ${bed.bed_number} — ${bed.status}`}
                                            className={`h-7 w-7 rounded border text-2xs font-medium inline-flex items-center justify-center ${BED_STYLE[bed.status]}`}>
                                            {bed.bed_number}
                                          </span>
                                        ))}
                                      </div>

                                      <div className="mt-2">
                                        <ProgressBar value={room.occupancy.occupied}
                                          max={room.occupancy.total || 1} />
                                        <div className="flex items-center justify-between mt-1">
                                          <span className="text-2xs text-slate-500 tnum">
                                            {room.occupancy.occupied}/{room.occupancy.total} beds
                                          </span>
                                          <span className="text-2xs font-medium text-slate-700 tnum">
                                            {inr(room.rent_amount)}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
