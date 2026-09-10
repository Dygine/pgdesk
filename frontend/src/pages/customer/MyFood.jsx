import { useState } from 'react'
import { UtensilsCrossed, Check, X } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { meApi } from '@/services/api/meApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, CardHeader, Button, StatusBadge, EmptyState, Skeleton, InlineAlert, StatCard,
} from '@/components/ui'
import { num, dateFmt } from '@/lib/format'

const MEALS = ['BREAKFAST', 'LUNCH', 'SNACK', 'DINNER']
const TONE = { ATTENDED: 'emerald', SKIPPED: 'slate', OPTED_OUT: 'amber', EXPECTED: 'brand' }

export default function MyFood() {
  const { success, error } = useToast()
  const { data, loading, error: failed, reload } = useApi(() => meApi.food(7), [])
  const [busy, setBusy] = useState(null)

  if (failed) {
    return (<><PageHeader title="Food" />
      <InlineAlert tone="error" title="Could not load">{failed.message}</InlineAlert></>)
  }
  if (loading && !data) {
    return (<><PageHeader title="Food" /><Skeleton className="h-64" /></>)
  }

  const choose = async (menu, status) => {
    setBusy(`${menu.on_date}-${menu.meal}`)
    try {
      await meApi.setMeal({ on_date: menu.on_date, meal: menu.meal, status })
      success(status === 'OPTED_OUT' ? 'Opted out' : 'Counted in',
        'The kitchen sees this in their counts.')
      reload()
    } catch (err) {
      error('Could not save that', err.message)
    } finally { setBusy(null) }
  }

  const byDate = data.menus.reduce((acc, m) => {
    (acc[m.on_date] ||= []).push(m)
    return acc
  }, {})
  const optedOut = data.history.filter((h) => h.status === 'OPTED_OUT').length
  const attended = data.history.filter((h) => h.status === 'ATTENDED').length

  return (
    <>
      <PageHeader title="Food"
        subtitle="This week's menu. Opting out early helps the kitchen cook the right amount." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-4">
        <StatCard label="Meals eaten" value={num(attended)} icon={UtensilsCrossed}
          tone="emerald" sub="in the last week" />
        <StatCard label="Opted out" value={num(optedOut)} tone="amber" />
        <StatCard label="Menus listed" value={num(data.menus.length)} tone="slate" />
        <StatCard label="Days shown" value={Object.keys(byDate).length} tone="brand" />
      </div>

      {Object.keys(byDate).length === 0 ? (
        <Card><EmptyState icon={UtensilsCrossed} title="No menu published yet"
          message="Once the kitchen publishes this week's menu it appears here." /></Card>
      ) : (
        <div className="space-y-4">
          {Object.entries(byDate).map(([on_date, menus]) => (
            <Card key={on_date}>
              <CardHeader title={`${new Date(`${on_date}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'long' })}, ${dateFmt(on_date)}`}
                subtitle={`${menus.length} meal${menus.length === 1 ? '' : 's'}`} />
              <div className="p-4 grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
                {MEALS.map((meal) => {
                  const m = menus.find((x) => x.meal === meal)
                  if (!m) return null
                  const key = `${m.on_date}-${m.meal}`
                  return (
                    <div key={meal} className="rounded-lg border border-line p-3.5">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <p className="text-xs font-semibold text-slate-800">
                          {m.label || meal}
                          {m.serve_from && <span className="font-normal text-slate-500 tnum"> · {m.serve_from}{m.serve_to ? `–${m.serve_to}` : ''}</span>}
                          {m.source === 'special' && <span className="ml-1.5 text-violet-700">· Special</span>}
                        </p>
                        {m.my_status && (
                          <StatusBadge status={m.my_status.replace('_', ' ')}
                            tone={TONE[m.my_status]} />
                        )}
                      </div>
                      <p className="text-sm text-slate-700 min-h-[2.5rem] whitespace-pre-line">{m.items}</p>
                      {m.notes && <p className="text-2xs text-violet-700 mt-1">{m.notes}</p>}
                      {m.calories && (
                        <p className="text-2xs text-slate-400 tnum mt-1">{m.calories} kcal</p>
                      )}
                      <div className="flex gap-1.5 mt-2.5">
                        <Button size="sm" icon={Check} className="flex-1"
                          loading={busy === key}
                          onClick={() => choose(m, 'EXPECTED')}>Count me in</Button>
                        <Button size="sm" icon={X} loading={busy === key}
                          onClick={() => choose(m, 'OPTED_OUT')}>Skip</Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
