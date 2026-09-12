/**
 * /features — the long-form capability list.
 *
 * Alternating rows rather than a grid of cards: each group has a paragraph and
 * five or six bullets, which is too much for a card and reads naturally beside
 * an illustration. Content comes from the `features_detail` block.
 */
import { ArrowRight, Check } from 'lucide-react'
import {
  useSite, useReveal, SectionHead, Cta, BTN_PRIMARY, BTN_GHOST,
} from '@/components/site/SiteLayout'
import { Illustration } from '@/components/site/Illustrations'

export default function Features() {
  const site = useSite()
  const root = useReveal([site])
  const B = site.blocks
  const d = B.features_detail || {}
  const groups = d.groups || []

  return (
    <div ref={root}>
      <section className="wash-brand border-b border-line">
        <div className="max-w-6xl mx-auto px-5 py-16 sm:py-20">
          <SectionHead eyebrow="Features" title={d.title || 'In detail'} intro={d.intro} />
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-5">
        {groups.map((g, i) => {
          const points = String(g.points || '').split(',').map((p) => p.trim()).filter(Boolean)
          const flip = i % 2 === 1
          return (
            <section key={i}
              className={`py-16 sm:py-20 grid lg:grid-cols-2 gap-12 items-center ${
                i ? 'border-t border-line' : ''}`}>
              <div className={`reveal ${flip ? 'lg:order-2' : ''}`}>
                <span className="inline-flex items-center justify-center h-8 px-3 rounded-full bg-accent-100 text-accent-800 text-xs font-bold tnum">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <h2 className="mt-4 text-2xl sm:text-3xl font-semibold tracking-[-.025em]">{g.title}</h2>
                <p className="mt-4 text-slate-600 leading-relaxed text-[17px]">{g.text}</p>
                <ul className="mt-7 grid sm:grid-cols-2 gap-x-6 gap-y-3">
                  {points.map((p) => (
                    <li key={p} className="flex gap-2.5 text-sm text-slate-700">
                      <span className="h-5 w-5 mt-0.5 shrink-0 rounded-md bg-brand-50 text-brand-700 inline-flex items-center justify-center">
                        <Check size={12} />
                      </span>
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
              <div className={`reveal reveal-2 ${flip ? 'lg:order-1' : ''}`}>
                <div className="rounded-3xl bg-brand-50/70 border border-line p-7 card-lift">
                  <Illustration name={g.illustration} className="w-full h-auto" />
                </div>
              </div>
            </section>
          )
        })}
      </div>

      <section className="bg-brand-950 text-white">
        <div className="max-w-6xl mx-auto px-5 py-16 text-center">
          <h2 className="reveal text-2xl sm:text-3xl font-semibold tracking-[-.025em]">
            {B.cta?.headline || 'Start with one branch.'}
          </h2>
          <p className="reveal reveal-1 mt-4 text-brand-100 max-w-xl mx-auto leading-relaxed">
            {B.cta?.text}
          </p>
          <div className="reveal reveal-2 mt-8 flex flex-wrap gap-3 justify-center">
            <Cta href={B.cta?.primary_href} icon={ArrowRight} className={BTN_PRIMARY}>
              {B.cta?.primary_label}
            </Cta>
            <Cta href="/pricing" className={BTN_GHOST}>See pricing</Cta>
          </div>
        </div>
      </section>
    </div>
  )
}
