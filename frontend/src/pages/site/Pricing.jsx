/**
 * /pricing — the plans, then the comparison table.
 *
 * The table is the reason this page exists. Four cards can carry five bullets
 * each; deciding between Professional and Business needs the row-by-row view,
 * and putting that on the home page would bury everything under it.
 */
import { ArrowRight, Check, Minus } from 'lucide-react'
import {
  useSite, useReveal, SectionHead, Cta, BTN_PRIMARY,
} from '@/components/site/SiteLayout'

const rupees = (n) => `₹${Number(n).toLocaleString('en-IN')}`
const KEYS = ['starter', 'professional', 'business', 'enterprise']

export default function Pricing() {
  const site = useSite()
  const root = useReveal([site])
  const B = site.blocks
  const p = B.pricing || {}
  const plans = p.plans || []
  const table = B.pricing_compare || {}

  const cell = (v) => {
    const s = String(v || '').trim()
    if (!s) return <Minus size={15} className="text-slate-300 mx-auto" />
    if (s.toLowerCase() === 'yes') return <Check size={16} className="text-emerald-600 mx-auto" />
    return <span className="text-sm text-slate-700 tnum">{s}</span>
  }

  return (
    <div ref={root}>
      <section className="wash-brand border-b border-line">
        <div className="max-w-6xl mx-auto px-5 py-16 sm:py-20">
          <SectionHead eyebrow="Pricing" title={p.title || 'Pricing'} intro={p.intro} center />
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-5 py-16">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {plans.map((plan, i) => {
            const popular = String(plan.popular || '').toLowerCase().startsWith('y')
            const feats = String(plan.features || '').split(',').map((f) => f.trim()).filter(Boolean)
            return (
              <div key={i}
                className={`reveal reveal-${i + 1} card-lift rounded-2xl bg-white p-6 flex flex-col ${
                  popular ? 'border-2 border-brand-600 shadow-pop' : 'border border-line hover:border-brand-200'}`}>
                {popular && (
                  <span className="self-start text-2xs font-bold uppercase tracking-wider bg-accent-400 text-brand-950 rounded-full px-3 py-1 mb-3">
                    Most chosen
                  </span>
                )}
                <h2 className="font-semibold text-lg">{plan.name}</h2>
                <p className="mt-3 text-3xl font-semibold tnum tracking-[-.02em]">
                  {rupees(plan.price)}
                  <span className="text-sm font-normal text-slate-500">/{plan.period || 'month'}</span>
                </p>
                {plan.summary && <p className="mt-1.5 text-xs text-slate-500">{plan.summary}</p>}
                <ul className="mt-5 space-y-2 flex-1">
                  {feats.map((f) => (
                    <li key={f} className="text-sm text-slate-600 flex gap-2">
                      <Check size={15} className="text-emerald-600 mt-0.5 shrink-0" />{f}
                    </li>
                  ))}
                </ul>
                <Cta href={p.cta_href}
                  className={`mt-6 inline-flex h-10 items-center justify-center rounded-xl font-semibold text-sm transition-colors ${
                    popular ? 'bg-brand-600 text-white hover:bg-brand-700'
                            : 'border border-line text-slate-700 hover:border-brand-300 hover:bg-brand-50'}`}>
                  {p.cta_label || 'Start free'}
                </Cta>
              </div>
            )
          })}
        </div>
        {p.note && <p className="reveal mt-6 text-xs text-slate-500 text-center">{p.note}</p>}
      </section>

      {table.rows?.length > 0 && (
        <section className="wash-soft border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-16">
            <SectionHead eyebrow="Compare" title={table.title || 'What each plan includes'} center />
            <div className="reveal mt-10 overflow-x-auto rounded-2xl border border-line bg-white">
              <table className="w-full min-w-[46rem] text-left">
                <thead>
                  <tr className="border-b border-line bg-slate-50/80">
                    <th className="px-5 py-4 text-xs font-semibold uppercase tracking-[.1em] text-slate-500">
                      Feature
                    </th>
                    {plans.map((pl) => (
                      <th key={pl.name} className="px-4 py-4 text-center text-sm font-semibold">
                        {pl.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, i) => (
                    <tr key={i} className="border-b border-line last:border-0 hover:bg-brand-50/40 transition-colors">
                      <th scope="row" className="px-5 py-3.5 text-sm font-medium text-slate-700">
                        {row.label}
                      </th>
                      {KEYS.map((k) => (
                        <td key={k} className="px-4 py-3.5 text-center">{cell(row[k])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      <section className="max-w-6xl mx-auto px-5 py-16 text-center">
        <h2 className="reveal text-2xl sm:text-3xl font-semibold tracking-[-.025em]">
          Not sure which one?
        </h2>
        <p className="reveal reveal-1 mt-3 text-slate-600 max-w-xl mx-auto">
          Start on the smallest plan. Moving up takes a moment and nothing is re-entered.
        </p>
        <div className="reveal reveal-2 mt-8 flex justify-center">
          <Cta href={p.cta_href} icon={ArrowRight} className={BTN_PRIMARY}>{p.cta_label}</Cta>
        </div>
      </section>
    </div>
  )
}
