import { useState } from 'react'
import { UtensilsCrossed, Save } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/lib/useApi'
import { foodApi } from '@/services/api/foodApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader, PermissionGuard } from '@/components/domain'
import {
  Card, CardHeader, Button, StatCard, StatusBadge, EmptyState, Skeleton,
  InlineAlert, Modal, FormField, Input, Select, Textarea,
} from '@/components/ui'
import { num, dateFmt, today } from '@/lib/format'

const MEALS = ['BREAKFAST', 'LUNCH', 'SNACK', 'DINNER']

export default function Food() {
  const { activeBranchId, can } = useAuth()
  const { success, error } = useToast()
  const [onDate, setOnDate] = useState(today())
  const [modal, setModal] = useState(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({})

  const branches = useApi(() => branchApi.list(), [], { enabled: can('branches.view') })
  const counts = useApi(() => foodApi.counts({ on_date: onDate, branch_id: activeBranchId }),
    [onDate, activeBranchId])
  const menus = useApi(
    () => foodApi.menus({ branch_id: activeBranchId, from_date: onDate, to_date: onDate }),
    [onDate, activeBranchId])

  const byMeal = Object.fromEntries((menus.data || []).map((m) => [m.meal, m]))
  const c = counts.data?.meals || {}
  const totalExpected = MEALS.reduce((a, m) => a + (c[m]?.expected_total || 0), 0)
  const totalAttended = MEALS.reduce((a, m) => a + (c[m]?.attended || 0), 0)
  const totalOptedOut = MEALS.reduce((a, m) => a + (c[m]?.opted_out || 0), 0)

  const openMenu = (meal) => {
    const existing = byMeal[meal]
    setF({ meal, branch_id: activeBranchId || branches.data?.items?.[0]?.id || '',
      on_date: onDate, items: existing?.items || '',
      calories: existing?.calories || '', notes: existing?.notes || '' })
    setModal(meal)
  }

  const save = async () => {
    if (!f.items?.trim()) return error('List what is being served.')
    if (!f.branch_id) return error('Choose a branch.')
    setBusy(true)
    try {
      await foodApi.saveMenu({
        branch_id: f.branch_id, on_date: f.on_date, meal: f.meal,
        items: f.items.trim(), calories: Number(f.calories) || null,
        notes: f.notes || null })
      success(`${f.meal.toLowerCase()} menu saved`)
      setModal(null)
      menus.reload()
    } catch (err) { error('Could not save the menu', err.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Food & mess"
        subtitle="Today's menu and how many meals the kitchen should cook." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Expected meals" value={num(totalExpected)}
          icon={UtensilsCrossed} tone="brand" />
        <StatCard label="Actually eaten" value={num(totalAttended)} tone="emerald" />
        <StatCard label="Opted out" value={num(totalOptedOut)} tone="amber" />
        <StatCard label="Menus published"
          value={`${Object.keys(byMeal).length}/4`} tone="slate" />
      </div>

      <Card className="mb-4">
        <div className="p-4 flex flex-col sm:flex-row gap-3 sm:items-end">
          <FormField label="Date" className="sm:w-56">
            <Input type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </FormField>
          <p className="text-xs text-slate-500 sm:pb-3">
            Residents opt out from their own portal; those numbers feed straight into
            the counts below.
          </p>
        </div>
      </Card>

      {menus.loading && !menus.data ? <Skeleton className="h-48" /> : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {MEALS.map((meal) => {
            const m = byMeal[meal]
            const stat = c[meal] || {}
            return (
              <Card key={meal}>
                <CardHeader title={meal.charAt(0) + meal.slice(1).toLowerCase()}
                  subtitle={m ? `${stat.expected_total || 0} expected` : 'No menu yet'} />
                <div className="p-4 space-y-3">
                  <p className="text-sm text-slate-700 min-h-[3rem]">
                    {m?.items || <span className="text-slate-400">Nothing published.</span>}
                  </p>
                  {m?.calories && (
                    <p className="text-2xs text-slate-400 tnum">{m.calories} kcal</p>
                  )}
                  <div className="grid grid-cols-3 gap-2 pt-2 border-t border-line text-center">
                    {[['Expected', stat.expected_total || 0],
                      ['Ate', stat.attended || 0],
                      ['Skipped', (stat.skipped || 0) + (stat.opted_out || 0)]].map(([k, v]) => (
                      <div key={k}>
                        <p className="text-sm font-semibold text-slate-900 tnum">{v}</p>
                        <p className="text-2xs text-slate-500">{k}</p>
                      </div>
                    ))}
                  </div>
                  <PermissionGuard perm="food.manage">
                    <Button size="sm" icon={Save} className="w-full"
                      onClick={() => openMenu(meal)}>
                      {m ? 'Edit menu' : 'Publish menu'}
                    </Button>
                  </PermissionGuard>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <Modal open={!!modal} onClose={() => setModal(null)} size="sm"
        title={`${modal?.charAt(0)}${modal?.slice(1).toLowerCase()} — ${dateFmt(onDate)}`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save menu</Button></>}>
        <div className="space-y-4">
          <FormField label="Branch" required>
            <Select value={f.branch_id || ''}
              onChange={(e) => setF({ ...f, branch_id: e.target.value })}>
              <option value="">Choose…</option>
              {(branches.data?.items || []).map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label="What is being served" required>
            <Textarea rows={3} value={f.items || ''}
              onChange={(e) => setF({ ...f, items: e.target.value })}
              placeholder="Rice, sambar, cabbage palya, curd" />
          </FormField>
          <FormField label="Calories" hint="Optional.">
            <Input inputMode="numeric" className="tnum" value={f.calories || ''}
              onChange={(e) => setF({ ...f, calories: e.target.value })} />
          </FormField>
          <FormField label="Notes">
            <Input value={f.notes || ''} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </FormField>
        </div>
      </Modal>
    </>
  )
}
