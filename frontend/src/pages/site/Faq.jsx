/**
 * /faq — questions, as an accordion.
 *
 * <details>/<summary> rather than a React accordion: it is keyboard accessible,
 * works with the page find-in-page, and needs no state. The chevron is rotated
 * with CSS off the open attribute.
 */
import { useState } from 'react'
import { ChevronDown, ArrowRight } from 'lucide-react'
import {
  useSite, useReveal, SectionHead, Cta, BTN_PRIMARY,
} from '@/components/site/SiteLayout'

export default function Faq() {
  const site = useSite()
  const root = useReveal([site])
  const B = site.blocks
  const faq = B.faq || {}
  const [q, setQ] = useState('')

  const items = (faq.items || []).filter((it) => {
    const term = q.trim().toLowerCase()
    if (!term) return true
    return `${it.q} ${it.a}`.toLowerCase().includes(term)
  })

  return (
    <div ref={root}>
      <section className="wash-brand border-b border-line">
        <div className="max-w-3xl mx-auto px-5 py-16 sm:py-20">
          <SectionHead eyebrow="Questions" title={faq.title || 'Questions'}
            intro="If the answer is not here, the phone number on the contact page reaches a person."
            center />
          <div className="reveal reveal-1 mt-8">
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search the questions"
              aria-label="Search the questions"
              className="w-full h-12 rounded-xl border border-line bg-white px-4 text-[15px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100 transition-shadow" />
          </div>
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-5 py-14">
        <div className="space-y-3">
          {items.map((it, i) => (
            <details key={i}
              className={`reveal reveal-${(i % 5) + 1} group card-lift rounded-2xl border border-line bg-white open:border-brand-200 open:shadow-lift`}>
              <summary className="flex items-center gap-4 cursor-pointer list-none px-6 py-5">
                <h2 className="font-medium text-[16px] flex-1">{it.q}</h2>
                <ChevronDown size={18}
                  className="text-slate-400 shrink-0 transition-transform duration-300 group-open:rotate-180" />
              </summary>
              <p className="px-6 pb-6 -mt-1 text-slate-600 leading-relaxed">{it.a}</p>
            </details>
          ))}
          {items.length === 0 && (
            <p className="text-center text-slate-500 py-10">
              Nothing matches “{q}”. Try fewer words, or ask us directly.
            </p>
          )}
        </div>

        <div className="reveal mt-12 rounded-2xl bg-brand-50 border border-brand-100 p-7 text-center">
          <h2 className="font-semibold text-lg">Still stuck?</h2>
          <p className="mt-2 text-slate-600">We answer email the same working day.</p>
          <div className="mt-6 flex justify-center">
            <Cta href="/contact" icon={ArrowRight} className={BTN_PRIMARY}>Contact us</Cta>
          </div>
        </div>
      </section>
    </div>
  )
}
