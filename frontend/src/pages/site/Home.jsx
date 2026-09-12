/**
 * The home page.
 *
 * An overview that ends in a decision, not an encyclopedia - the depth lives on
 * /features, /pricing and /faq, and each section here points at the page that
 * carries it. A homepage that says everything is a homepage nobody finishes.
 *
 * All copy comes from the database (Master -> Website). This file owns layout
 * and nothing else.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight, Check, BedDouble, Users, IndianRupee, Smartphone, Search,
  ShieldCheck, Download, Quote,
} from 'lucide-react'
import {
  useSite, useReveal, SectionHead, Cta, BTN_PRIMARY, BTN_GHOST, BTN_GOLD,
} from '@/components/site/SiteLayout'
import { Illustration } from '@/components/site/Illustrations'

const ICONS = {
  bed: BedDouble, users: Users, rupee: IndianRupee,
  portal: Smartphone, search: Search, shield: ShieldCheck,
}
const rupees = (n) => `₹${Number(n).toLocaleString('en-IN')}`

export default function Home() {
  const site = useSite()
  const root = useReveal([site])
  const B = site.blocks
  const img = (slot) => site.images[slot] || null

  const hero = B.hero || {}
  const heroImg = img(hero.image_slot)

  return (
    <div ref={root}>

      {/* ----------------------------------------------------------- hero */}
      <section className="wash-brand border-b border-line">
        <div className="max-w-6xl mx-auto px-5 pt-16 pb-16 sm:pt-24 sm:pb-20 grid lg:grid-cols-[1.05fr_1fr] gap-14 items-center">
          <div className="reveal">
            <p className="inline-flex items-center gap-2 rounded-full bg-white border border-accent-200 px-3.5 py-1.5 text-xs font-medium text-accent-700 shadow-card">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-400" />
              Built for PG and hostel owners in India
            </p>
            <h1 className="mt-6 text-[2.25rem] sm:text-[3.25rem] font-semibold tracking-[-.03em] leading-[1.05]">
              {hero.headline}
            </h1>
            <p className="mt-6 text-lg text-slate-600 leading-relaxed max-w-xl">
              {hero.subheadline}
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Cta href={hero.primary_href} icon={ArrowRight} className={BTN_PRIMARY}>
                {hero.primary_label}
              </Cta>
              <Cta href={hero.secondary_href} className={BTN_GHOST}>{hero.secondary_label}</Cta>
            </div>
            <p className="mt-5 text-sm text-slate-500">
              Nothing to install · Works on any phone · Your data stays yours
            </p>
          </div>

          <div className="reveal reveal-2">
            {heroImg?.src && !hero.illustration
              ? <img src={heroImg.src} alt={heroImg.alt_text || ''}
                  className="w-full rounded-2xl border border-line shadow-pop" />
              : <Illustration name={hero.illustration || 'room'} className="w-full h-auto drop-shadow-xl" />}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- trust */}
      {B.trust?.items?.length > 0 && (
        <section className="bg-brand-950 text-white">
          <div className="max-w-6xl mx-auto px-5 py-11 grid grid-cols-2 lg:grid-cols-4 gap-8">
            {B.trust.items.map((t, i) => (
              <div key={i} className={`reveal reveal-${(i % 4) + 1}`}>
                <p className="text-lg font-semibold tracking-[-.01em] text-accent-300">{t.value}</p>
                <p className="text-sm text-brand-100/85 mt-1 leading-snug">{t.label}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* -------------------------------------------------------- problem */}
      {B.problem?.items?.length > 0 && (
        <section className="max-w-6xl mx-auto px-5 py-20">
          <SectionHead eyebrow="The everyday" title={B.problem.title} intro={B.problem.intro} />
          <div className="mt-10 grid sm:grid-cols-2 gap-4">
            {B.problem.items.map((it, i) => (
              <div key={i}
                className={`reveal reveal-${(i % 4) + 1} card-lift rounded-2xl border border-line bg-white p-6 hover:border-brand-200`}>
                <p className="text-sm text-slate-400 line-through decoration-slate-300">{it.before}</p>
                <p className="mt-3 font-medium flex gap-2.5 leading-snug">
                  <span className="h-6 w-6 shrink-0 rounded-full bg-emerald-50 text-emerald-600 inline-flex items-center justify-center">
                    <Check size={14} />
                  </span>
                  {it.after}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------- features */}
      {B.features?.items?.length > 0 && (
        <section className="wash-soft border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-20">
            <SectionHead eyebrow="What's inside" title={B.features.title} />
            <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {B.features.items.map((f, i) => {
                const Icon = ICONS[f.icon] || BedDouble
                return (
                  <div key={i}
                    className={`reveal reveal-${(i % 3) + 1} card-lift rounded-2xl border border-line bg-white overflow-hidden hover:border-brand-200 hover:shadow-lift`}>
                    {f.illustration && (
                      <div className="bg-brand-50/60 px-5 pt-5">
                        <Illustration name={f.illustration} className="w-full h-auto" />
                      </div>
                    )}
                    <div className="p-6">
                      <span className="h-10 w-10 rounded-xl bg-brand-600 text-white inline-flex items-center justify-center shadow-card">
                        <Icon size={19} />
                      </span>
                      <h3 className="mt-4 font-semibold text-[17px]">{f.title}</h3>
                      <p className="mt-2 text-sm text-slate-600 leading-relaxed">{f.text}</p>
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="reveal mt-10">
              <Link to="/features"
                className="inline-flex items-center gap-2 font-semibold text-brand-700 hover:text-brand-800 group">
                See everything it does
                <ArrowRight size={17} className="transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------ how */}
      {B.how?.steps?.length > 0 && (
        <section className="max-w-6xl mx-auto px-5 py-20">
          <SectionHead eyebrow="Getting started" title={B.how.title} center />
          <ol className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {B.how.steps.map((s, i) => (
              <li key={i}
                className={`reveal reveal-${i + 1} card-lift relative rounded-2xl border border-line bg-white p-6 hover:border-accent-300`}>
                <span className="absolute -top-4 left-6 h-9 w-9 rounded-xl bg-accent-400 text-brand-950 font-bold inline-flex items-center justify-center shadow-lift">
                  {i + 1}
                </span>
                <h3 className="mt-4 font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{s.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* -------------------------------------------------------- pricing */}
      {B.pricing?.plans?.length > 0 && (
        <section className="wash-soft border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-20">
            <SectionHead eyebrow="Pricing" title={B.pricing.title} intro={B.pricing.intro} center />
            <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {B.pricing.plans.map((p, i) => {
                const popular = String(p.popular || '').toLowerCase().startsWith('y')
                const feats = String(p.features || '').split(',').map((f) => f.trim()).filter(Boolean)
                return (
                  <div key={i}
                    className={`reveal reveal-${i + 1} card-lift rounded-2xl bg-white p-6 flex flex-col ${
                      popular ? 'border-2 border-brand-600 shadow-pop' : 'border border-line hover:border-brand-200'}`}>
                    {popular && (
                      <span className="self-start text-2xs font-bold uppercase tracking-wider bg-accent-400 text-brand-950 rounded-full px-3 py-1 mb-3">
                        Most chosen
                      </span>
                    )}
                    <h3 className="font-semibold text-lg">{p.name}</h3>
                    <p className="mt-3 text-3xl font-semibold tnum tracking-[-.02em]">
                      {rupees(p.price)}
                      <span className="text-sm font-normal text-slate-500">/{p.period || 'month'}</span>
                    </p>
                    {p.summary && <p className="mt-1.5 text-xs text-slate-500">{p.summary}</p>}
                    <ul className="mt-5 space-y-2 flex-1">
                      {feats.slice(0, 5).map((f) => (
                        <li key={f} className="text-sm text-slate-600 flex gap-2">
                          <Check size={15} className="text-emerald-600 mt-0.5 shrink-0" />{f}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
            <div className="reveal mt-10 flex flex-wrap items-center justify-center gap-4">
              <Cta href={B.pricing.cta_href} icon={ArrowRight} className={BTN_PRIMARY}>
                {B.pricing.cta_label}
              </Cta>
              <Link to="/pricing" className="font-semibold text-brand-700 hover:text-brand-800">
                Compare the plans
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* --------------------------------------------------- testimonials */}
      {B.testimonials?.items?.length > 0 && (
        <section className="max-w-6xl mx-auto px-5 py-20">
          <SectionHead eyebrow="In their words" title={B.testimonials.title} center />
          <div className="mt-10 grid sm:grid-cols-3 gap-5">
            {B.testimonials.items.map((t, i) => (
              <figure key={i}
                className={`reveal reveal-${(i % 3) + 1} card-lift rounded-2xl border border-line bg-white p-6 hover:border-accent-300`}>
                <Quote size={22} className="text-accent-400" />
                <blockquote className="mt-3 text-slate-700 leading-relaxed">{t.quote}</blockquote>
                <figcaption className="mt-5 text-sm">
                  <span className="font-semibold">{t.name}</span>
                  <span className="block text-slate-500 text-xs mt-0.5">
                    {[t.pg, t.city].filter(Boolean).join(' · ')}
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------ cta */}
      {B.cta && (
        <section className="max-w-6xl mx-auto px-5 py-16">
          <div className="reveal relative overflow-hidden rounded-3xl bg-brand-700 text-white px-8 py-14 sm:px-14 sm:py-16">
            <div className="absolute -right-16 -top-16 h-72 w-72 rounded-full bg-accent-400/20 blur-2xl" />
            <div className="absolute -left-20 -bottom-20 h-72 w-72 rounded-full bg-brand-400/25 blur-2xl" />
            <div className="relative grid lg:grid-cols-[1.4fr_1fr] gap-10 items-center">
              <div>
                <h2 className="text-2xl sm:text-4xl font-semibold tracking-[-.025em] leading-tight">
                  {B.cta.headline}
                </h2>
                <p className="mt-4 text-brand-100 max-w-xl leading-relaxed text-[17px]">{B.cta.text}</p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <Cta href={B.cta.primary_href} icon={ArrowRight} className={BTN_GOLD}>
                    {B.cta.primary_label}
                  </Cta>
                  <Cta href={B.cta.secondary_href} icon={Download}
                    className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/35 px-6 font-medium text-white hover:bg-white/10 transition-colors">
                    {B.cta.secondary_label}
                  </Cta>
                </div>
              </div>
              <div className="hidden lg:block float-slow">
                <Illustration name="map" className="w-full h-auto opacity-95" />
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
