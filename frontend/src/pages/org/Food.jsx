/**
 * Food & mess.
 *
 * The kitchen works from a weekly chart - Monday breakfast, Monday lunch, and
 * so on - that repeats every week. That chart is now the menu. A special for a
 * single date (a festival lunch) overrides it for that day only, and specials
 * are deleted automatically a week after their date, so the only thing stored
 * long-term is the one weekly menu.
 *
 * Which meals the PG serves, what it calls them ("Evening tea") and when, are
 * the PG's own - set under "Meals & timings".
 */
import { useEffect, useMemo, useState } from 'react'
import { UtensilsCrossed, Save, Sparkles, Undo2, Copy, CalendarDays } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { foodApi } from '@/services/api/foodApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, Skeleton,
  InlineAlert, Modal, FormField, Input, Select, Textarea, Tabs, Toggle,
} from '@/components/ui'
import { num, dateFmt, today } from '@/lib/format'

const MEALS = ['BREAKFAST', 'LUNCH', 'SNACK', 'DINNER']
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const emptyGrid = () => DAYS.map(() => Object.fromEntries(MEALS.map((m) => [m, ''])))
const weekdayOf = (ymd) => (new Date(`${ymd}T00:00:00`).getDay() + 6) % 7   // Monday = 0

export default function Food() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [tab, setTab] = useState('day')
  const [onDate, setOnDate] = useState(today())
  const [pickedBranch, setPickedBranch] = useState('')
  const [special, setSpecial] = useState(null)       // { meal, items, notes }
  const [grid, setGrid] = useState(emptyGrid)
  const [dirty, setDirty] = useState(false)
  const [sched, setSched] = useState(null)
  const [busy, setBusy] = useState(false)

  const branches = useApi(() => branchApi.list(), [],
    { enabled: can('branches.view'), initial: { items: [] } })
  const branchId = activeBranchId || pickedBranch || branches.data?.items?.[0]?.id || ''

  const schedule = useApi(() => foodApi.schedule(), [])
  const counts = useApi(() => foodApi.counts({ on_date: onDate, branch_id: activeBranchId }),
    [onDate, activeBranchId])
  const dayMenu = useApi(
    () => (branchId ? foodApi.effective({ branch_id: branchId, from_date: onDate, to_date: onDate })
      : Promise.resolve([])), [branchId, onDate])
  const week = useApi(() => (branchId ? foodApi.week(branchId) : Promise.resolve(null)), [branchId])

  useEffect(() => { if (schedule.data) setSched(JSON.parse(JSON.stringify(schedule.data))) }, [schedule.data])
  useEffect(() => {
    if (!week.data) return
    const g = emptyGrid()
    week.data.entries.forEach((e) => { g[e.weekday][e.meal] = e.items })
    setGrid(g)
    setDirty(false)
  }, [week.data])

  const meals = useMemo(() => MEALS.filter((m) => (schedule.data?.[m]?.enabled ?? true)), [schedule.data])
  const label = (m) => schedule.data?.[m]?.label || m.charAt(0) + m.slice(1).toLowerCase()
  const byMeal = Object.fromEntries((dayMenu.data || []).map((m) => [m.meal, m]))
  const c = counts.data?.meals || {}
  const totals = ['expected_total', 'attended', 'opted_out'].map((k) =>
    MEALS.reduce((a, m) => a + (c[m]?.[k] || 0), 0))

  const branchPicker = !activeBranchId && (branches.data?.items || []).length > 1 && (
    <FormField label="Branch" className="sm:w-56">
      <Select value={branchId} onChange={(e) => setPickedBranch(e.target.value)}>
        {(branches.data?.items || []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
      </Select>
    </FormField>
  )

  /* ------------------------------------------------------------- actions */
  const saveSpecial = async () => {
    if (!special.items?.trim()) return error('List what is being served.')
    setBusy(true)
    try {
      await foodApi.saveMenu({ branch_id: branchId, on_date: onDate, meal: special.meal,
        items: special.items.trim(), notes: special.notes || null })
      success(`${label(special.meal)} special saved for ${dateFmt(onDate)}`)
      setSpecial(null)
      dayMenu.reload()
    } catch (err) { error('Could not save the special', err.message) }
    finally { setBusy(false) }
  }
  const removeSpecial = async (m) => {
    try {
      await foodApi.deleteSpecial(m.id)
      success('Special removed', 'The weekly menu applies to this day again.')
      dayMenu.reload()
    } catch (err) { error('Could not remove it', err.message) }
  }
  const setCell = (day, meal, value) => {
    setGrid((g) => g.map((row, i) => (i === day ? { ...row, [meal]: value } : row)))
    setDirty(true)
  }
  const copyDayToAll = (day) => {
    setGrid((g) => g.map(() => ({ ...g[day] })))
    setDirty(true)
  }
  const saveWeek = async () => {
    setBusy(true)
    try {
      const entries = []
      grid.forEach((row, weekday) => MEALS.forEach((meal) =>
        entries.push({ weekday, meal, items: row[meal] || '' })))
      await foodApi.saveWeek({ branch_id: branchId, entries })
      success('Weekly menu saved', 'It repeats every week until you change it.')
      week.reload(); dayMenu.reload()
    } catch (err) { error('Could not save the weekly menu', err.message) }
    finally { setBusy(false) }
  }
  const saveSchedule = async () => {
    setBusy(true)
    try {
      await foodApi.saveSchedule(sched)
      success('Meals & timings saved')
      schedule.reload(); dayMenu.reload()
    } catch (err) { error('Could not save', err.message) }
    finally { setBusy(false) }
  }

  const manage = can('food.manage')

  return (
    <>
      <PageHeader title="Food & mess"
        subtitle="Set the weekly menu once - it repeats every week. Add a special for any single day." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Expected meals" value={num(totals[0])} icon={UtensilsCrossed} tone="brand"
          sub={dateFmt(onDate)} />
        <StatCard label="Actually eaten" value={num(totals[1])} tone="emerald" />
        <StatCard label="Opted out" value={num(totals[2])} tone="amber" />
        <StatCard label="Meals served" value={`${meals.length} a day`} tone="slate" />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'day', label: 'Day view' },
        { value: 'week', label: 'Weekly menu' },
        { value: 'meals', label: 'Meals & timings' },
      ]} />

      <div className="mt-4">
        {/* ------------------------------------------------------ day view */}
        {tab === 'day' && (
          <>
            <Card className="mb-4">
              <div className="p-4 flex flex-col sm:flex-row gap-3 sm:items-end">
                <FormField label="Date" className="sm:w-56">
                  <Input type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
                </FormField>
                {branchPicker}
                <p className="text-xs text-slate-500 sm:pb-3">
                  {DAYS[weekdayOf(onDate)]}. Residents opt out from their own app; those numbers
                  feed straight into the counts.
                </p>
              </div>
            </Card>
            {dayMenu.loading && !dayMenu.data ? <Skeleton className="h-48" /> : (
              <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {meals.map((meal) => {
                  const m = byMeal[meal]
                  const stat = c[meal] || {}
                  const time = schedule.data?.[meal]
                  return (
                    <Card key={meal}>
                      <CardHeader title={label(meal)}
                        subtitle={time?.serve_from ? `${time.serve_from} – ${time.serve_to || ''}` : undefined}
                        action={m && <StatusBadge status={m.source === 'special' ? 'Special' : 'Weekly'}
                          tone={m.source === 'special' ? 'violet' : 'slate'} />} />
                      <div className="p-4 space-y-3">
                        <p className="text-sm text-slate-700 min-h-[3rem] whitespace-pre-line">
                          {m?.items || <span className="text-slate-400">Nothing on the weekly menu for {DAYS[weekdayOf(onDate)]}.</span>}
                        </p>
                        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-line text-center">
                          {[['Expected', stat.expected_total || 0], ['Ate', stat.attended || 0],
                            ['Skipped', (stat.skipped || 0) + (stat.opted_out || 0)]].map(([k, v]) => (
                            <div key={k}>
                              <p className="text-sm font-semibold text-slate-900 tnum">{v}</p>
                              <p className="text-2xs text-slate-500">{k}</p>
                            </div>
                          ))}
                        </div>
                        {manage && branchId && (
                          m?.source === 'special' ? (
                            <div className="flex gap-2">
                              <Button size="sm" icon={Sparkles} className="flex-1"
                                onClick={() => setSpecial({ meal, items: m.items, notes: m.notes || '' })}>
                                Edit special</Button>
                              <Button size="sm" variant="ghost" icon={Undo2}
                                onClick={() => removeSpecial(m)}>Use weekly</Button>
                            </div>
                          ) : (
                            <Button size="sm" icon={Sparkles} className="w-full"
                              onClick={() => setSpecial({ meal, items: m?.items || '', notes: '' })}>
                              Special for this day</Button>
                          )
                        )}
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </>
        )}

        {/* --------------------------------------------------- weekly menu */}
        {tab === 'week' && (
          <Card>
            <CardHeader title="Weekly menu"
              subtitle="Repeats every week. Leave a box empty if that meal is not served that day."
              action={manage && <Button variant="primary" icon={Save} loading={busy}
                disabled={!dirty || !branchId} onClick={saveWeek}>Save week</Button>} />
            {branchPicker && <div className="px-4 sm:px-5 pt-4">{branchPicker}</div>}
            {!branchId ? (
              <EmptyState compact title="Add a branch first" />
            ) : week.loading && !week.data ? <div className="p-5"><Skeleton className="h-64" /></div> : (
              <div className="p-3 sm:p-5 space-y-3">
                {DAYS.map((day, d) => (
                  <div key={day} className={`rounded-xl border p-3 sm:p-4 ${d === weekdayOf(today()) ? 'border-brand-300 bg-brand-50/30' : 'border-line'}`}>
                    <div className="flex items-center justify-between gap-2 mb-2.5">
                      <p className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                        <CalendarDays size={15} className="text-slate-400" />{day}
                        {d === weekdayOf(today()) && <StatusBadge status="Today" tone="brand" />}
                      </p>
                      {manage && (
                        <button onClick={() => copyDayToAll(d)}
                          className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1">
                          <Copy size={12} /> Copy to every day</button>
                      )}
                    </div>
                    <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2.5">
                      {meals.map((meal) => (
                        <label key={meal} className="block">
                          <span className="block text-2xs font-medium text-slate-500 mb-1">{label(meal)}</span>
                          <Textarea rows={2} value={grid[d][meal]} disabled={!manage}
                            onChange={(e) => setCell(d, meal, e.target.value)}
                            placeholder={manage ? 'e.g. Idli, sambar, chutney' : '—'}
                            className="text-[13px] min-h-[3.25rem]" />
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                <InlineAlert tone="info">
                  One-day specials are deleted automatically a week after their date. The weekly
                  menu stays until you change it.
                </InlineAlert>
              </div>
            )}
          </Card>
        )}

        {/* ----------------------------------------------- meals & timings */}
        {tab === 'meals' && (
          <Card className="max-w-3xl">
            <CardHeader title="Meals & timings"
              subtitle="Which meals you serve, what residents see them called, and when."
              action={manage && <Button variant="primary" icon={Save} loading={busy}
                disabled={!sched} onClick={saveSchedule}>Save</Button>} />
            {!sched ? <div className="p-5"><Skeleton className="h-40" /></div> : (
              <div className="divide-y divide-line">
                {MEALS.map((meal) => {
                  const row = sched[meal]
                  const upd = (k, v) => setSched((s) => ({ ...s, [meal]: { ...s[meal], [k]: v } }))
                  return (
                    <div key={meal} className="px-4 sm:px-5 py-3 grid sm:grid-cols-[12rem_1fr_7rem_7rem] gap-3 items-end">
                      <Toggle checked={row.enabled} disabled={!manage}
                        onChange={(v) => upd('enabled', v)}
                        label={meal.charAt(0) + meal.slice(1).toLowerCase()}
                        description={row.enabled ? 'Served' : 'Not served'} />
                      <FormField label="Called">
                        <Input value={row.label || ''} maxLength={30} disabled={!manage || !row.enabled}
                          onChange={(e) => upd('label', e.target.value)} />
                      </FormField>
                      <FormField label="From">
                        <Input type="time" value={row.serve_from || ''} disabled={!manage || !row.enabled}
                          onChange={(e) => upd('serve_from', e.target.value)} />
                      </FormField>
                      <FormField label="To">
                        <Input type="time" value={row.serve_to || ''} disabled={!manage || !row.enabled}
                          onChange={(e) => upd('serve_to', e.target.value)} />
                      </FormField>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        )}
      </div>

      <Modal open={!!special} onClose={() => setSpecial(null)} size="sm"
        title={special ? `${label(special.meal)} special` : ''}
        subtitle={`Only for ${DAYS[weekdayOf(onDate)]}, ${dateFmt(onDate)}. The weekly menu is not changed.`}
        footer={<><Button onClick={() => setSpecial(null)}>Cancel</Button>
          <PermissionGuard perm="food.manage">
            <Button variant="primary" loading={busy} onClick={saveSpecial}>Save special</Button>
          </PermissionGuard></>}>
        {special && (
          <div className="space-y-4">
            <FormField label="What is being served" required>
              <Textarea rows={3} value={special.items}
                onChange={(e) => setSpecial({ ...special, items: e.target.value })}
                placeholder="Veg biryani, raita, gulab jamun" />
            </FormField>
            <FormField label="Note for residents">
              <Input value={special.notes || ''} placeholder="Ganesh Chaturthi lunch"
                onChange={(e) => setSpecial({ ...special, notes: e.target.value })} />
            </FormField>
          </div>
        )}
      </Modal>
    </>
  )
}
