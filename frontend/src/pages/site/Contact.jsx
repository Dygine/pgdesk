/**
 * /contact — how to reach a person.
 *
 * Empty fields are omitted rather than rendered blank: a contact page showing
 * "Phone:" with nothing after it looks abandoned. Until the master admin fills
 * the phone and address in under Master -> Website, this page shows only what
 * actually exists.
 */
import { Phone, Mail, MapPin, Clock, MessageCircle, ArrowRight } from 'lucide-react'
import {
  useSite, useReveal, SectionHead, Cta, BTN_PRIMARY, BTN_GHOST,
} from '@/components/site/SiteLayout'
import { Illustration } from '@/components/site/Illustrations'

const waDigits = (phone) => {
  const d = String(phone || '').replace(/\D/g, '')
  return d.length === 10 ? `91${d}` : d
}

export default function Contact() {
  const site = useSite()
  const root = useReveal([site])
  const B = site.blocks
  const c = B.contact || {}

  const cards = [
    c.phone && { icon: Phone, label: 'Phone', value: c.phone, href: `tel:${c.phone}` },
    c.whatsapp && { icon: MessageCircle, label: 'WhatsApp', value: c.whatsapp,
                    href: `https://wa.me/${waDigits(c.whatsapp)}` },
    c.email && { icon: Mail, label: 'Email', value: c.email, href: `mailto:${c.email}` },
    c.hours && { icon: Clock, label: 'Hours', value: c.hours },
    c.address && { icon: MapPin, label: 'Address', value: c.address, wide: true },
  ].filter(Boolean)

  return (
    <div ref={root}>
      <section className="wash-brand border-b border-line">
        <div className="max-w-6xl mx-auto px-5 py-16 sm:py-20">
          <SectionHead eyebrow="Contact" title={c.title || 'Talk to us'}
            intro="A real person answers. Tell us how many beds you run and we will tell you honestly whether this fits."
            center />
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-5 py-16 grid lg:grid-cols-[1.2fr_1fr] gap-14 items-start">
        <div>
          <div className="grid sm:grid-cols-2 gap-4">
            {cards.map((it, i) => {
              const Icon = it.icon
              const inner = (
                <>
                  <span className="h-11 w-11 rounded-xl bg-brand-600 text-white inline-flex items-center justify-center shadow-card">
                    <Icon size={19} />
                  </span>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-[.12em] text-slate-400">
                    {it.label}
                  </p>
                  <p className="mt-1 font-medium text-slate-900 break-words">{it.value}</p>
                </>
              )
              const cls = `reveal reveal-${(i % 4) + 1} card-lift rounded-2xl border border-line bg-white p-6 block hover:border-brand-200 ${
                it.wide ? 'sm:col-span-2' : ''}`
              return it.href
                ? <a key={it.label} href={it.href} className={cls}>{inner}</a>
                : <div key={it.label} className={cls}>{inner}</div>
            })}
          </div>

          {cards.length === 0 && (
            <div className="reveal rounded-2xl border border-dashed border-line p-8 text-center text-slate-500">
              No contact details have been added yet. They are set under
              Master → Website → Contact.
            </div>
          )}

          <div className="reveal mt-10 rounded-2xl bg-brand-950 text-white p-8">
            <h2 className="text-xl font-semibold tracking-[-.02em]">Run a PG already?</h2>
            <p className="mt-2.5 text-brand-100 leading-relaxed">
              You do not need to talk to anyone first. Create an account, add one
              branch, and see a month through before deciding.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Cta href="/signup" icon={ArrowRight} className={BTN_PRIMARY}>Create an account</Cta>
              <Cta href="/pricing" className={BTN_GHOST}>See pricing</Cta>
            </div>
          </div>
        </div>

        <div className="reveal reveal-2">
          <div className="rounded-3xl bg-brand-50/70 border border-line p-8 float-slow">
            <Illustration name="portal" className="w-full h-auto" />
          </div>
          <p className="mt-5 text-sm text-slate-500 leading-relaxed">
            Looking for a place to stay rather than software to run one?
            {' '}
            <Cta href="/find-pg" className="font-semibold text-brand-700 hover:text-brand-800">
              Find a PG near you
            </Cta>.
          </p>
        </div>
      </section>
    </div>
  )
}
