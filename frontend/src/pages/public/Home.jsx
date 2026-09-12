/**
 * The public website.
 *
 * Every word and every picture on this page comes from the database, edited by
 * the master admin under Master -> Website. Nothing here is hard-coded copy -
 * the component decides *layout*, the content decides *what it says*. That
 * separation is the whole point: a price change or a new phone number should
 * never be a code change, a build and a deploy.
 *
 * Blocks the editor has never touched fall back to presets held on the server
 * (backend/app/services/site_service.py), so the page is complete and coherent
 * from the very first load, before anyone has edited anything.
 *
 * On SEO, honestly
 * ----------------
 * This is a React page, so the first paint needs JavaScript. Searching the
 * brand name will find it once Search Console has indexed it - Google renders
 * JS, and there is no competition for "pgguru". Competing for "PG management
 * software" against sites with years of authority needs server-rendered HTML
 * and real inbound links, and no amount of markup here substitutes for that.
 * What this page does do properly: one h1, a real heading order, descriptive
 * alt text on every image, and the title/description/canonical written into the
 * document head from the `seo` block.
 *
 * A block that fails to load is not a broken page. If the API is unreachable
 * the presets bundled below render instead, so the site is never a white screen
 * because a database was asleep.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BedDouble, Users, IndianRupee, Smartphone, Search, ShieldCheck,
  Check, Phone, Mail, MapPin, Clock, Menu, X, Download,
} from 'lucide-react'
import { siteApi } from '@/services/api/siteApi'
import { PLANS } from '@/data/plans'

/* Fallbacks used only when the API cannot be reached at all. Kept deliberately
   short - the real presets live on the server, where the editor can see them. */
const OFFLINE = {
  brand: { name: 'PGuru', tagline: 'PG and hostel operations, on one screen' },
  hero: {
    headline: 'Every bed, every rupee, every branch.',
    subheadline: 'Rooms, residents, rent and complaints in one place.',
    primary_label: 'Open the app', primary_href: '/app/login',
  },
}

const ICONS = {
  bed: BedDouble, users: Users, rupee: IndianRupee, portal: Smartphone,
  search: Search, shield: ShieldCheck,
}

const rupees = (n) => `₹${Number(n).toLocaleString('en-IN')}`

/** Internal links go through the router; anything else is a plain anchor. */
function Cta({ href, children, className, icon: Icon }) {
  const inner = (<>{children}{Icon ? <Icon size={16} /> : null}</>)
  if (!href) return null
  return href.startsWith('/') && !href.endsWith('.apk')
    ? <Link to={href} className={className}>{inner}</Link>
    : <a href={href} className={className}>{inner}</a>
}

export default function Home() {
  const [site, setSite] = useState(null)
  const [failed, setFailed] = useState(false)
  const [menu, setMenu] = useState(false)

  useEffect(() => {
    let dead = false
    ;(async () => {
      try {
        const data = await siteApi.content()
        if (!dead) setSite(data)
      } catch {
        if (!dead) setFailed(true)
      }
    })()
    return () => { dead = true }
  }, [])

  const B = site?.blocks || (failed ? OFFLINE : null)
  const images = site?.images || {}
  const img = (slot) => images[slot] || null

  /* The document head, from the `seo` block. Written imperatively because this
     app has no SSR and no head manager; a crawler that renders JS reads the
     result either way. */
  useEffect(() => {
    const seo = B?.seo
    if (!seo) return
    if (seo.title) document.title = seo.title
    const meta = (name, value, attr = 'name') => {
      if (!value) return
      let tag = document.head.querySelector(`meta[${attr}="${name}"]`)
      if (!tag) {
        tag = document.createElement('meta')
        tag.setAttribute(attr, name)
        document.head.appendChild(tag)
      }
      tag.setAttribute('content', value)
    }
    meta('description', seo.description)
    meta('keywords', seo.keywords)
    meta('og:title', seo.title, 'property')
    meta('og:description', seo.description, 'property')
    meta('og:type', 'website', 'property')
    const social = images[seo.social_image_slot]?.src
    if (social) meta('og:image', social, 'property')
    if (seo.canonical) {
      let link = document.head.querySelector('link[rel="canonical"]')
      if (!link) {
        link = document.createElement('link')
        link.setAttribute('rel', 'canonical')
        document.head.appendChild(link)
      }
      link.setAttribute('href', seo.canonical)
    }
  }, [B, images])

  if (!B) {
    return (
      <div className="min-h-dvh bg-white flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-brand-200 border-t-brand-700 animate-spin" />
      </div>
    )
  }

  const brand = B.brand || {}
  const hero = B.hero || {}
  const heroImg = img(hero.image_slot)

  return (
    <div className="min-h-dvh bg-white text-slate-900">

      {/* ------------------------------------------------------------ nav */}
      <header className="sticky top-0 z-30 bg-white/92 backdrop-blur border-b border-line safe-t">
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2.5 min-w-0">
            {img(brand.logo_slot)?.src
              ? <img src={img(brand.logo_slot).src} alt={brand.name || 'Logo'} className="h-8 w-auto" />
              : <span className="h-8 w-8 rounded-lg bg-brand-700 text-white inline-flex items-center justify-center font-bold">
                  {(brand.name || 'P')[0]}
                </span>}
            <span className="font-semibold tracking-[-.01em] truncate">{brand.name}</span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 ml-6 text-sm text-slate-600">
            <a href="#features" className="hover:text-slate-900">Features</a>
            <a href="#pricing" className="hover:text-slate-900">Pricing</a>
            <a href="#faq" className="hover:text-slate-900">Questions</a>
            <a href="#contact" className="hover:text-slate-900">Contact</a>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <Link to="/find-pg"
              className="hidden sm:inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3.5 text-sm font-medium hover:bg-slate-50">
              <Search size={15} /> Find a PG
            </Link>
            <Link to="/login"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-700 px-4 text-sm font-semibold text-white hover:bg-brand-800">
              Sign in
            </Link>
            <button type="button" onClick={() => setMenu((v) => !v)}
              aria-label="Menu" aria-expanded={menu}
              className="md:hidden h-9 w-9 inline-flex items-center justify-center rounded-lg border border-line">
              {menu ? <X size={17} /> : <Menu size={17} />}
            </button>
          </div>
        </div>
        {menu && (
          <nav className="md:hidden border-t border-line bg-white px-5 py-3 flex flex-col gap-3 text-sm">
            {[['#features', 'Features'], ['#pricing', 'Pricing'], ['#faq', 'Questions'],
              ['#contact', 'Contact']].map(([h, l]) => (
              <a key={h} href={h} onClick={() => setMenu(false)} className="text-slate-700">{l}</a>
            ))}
            <Link to="/find-pg" className="text-slate-700">Find a PG</Link>
          </nav>
        )}
      </header>

      {/* ----------------------------------------------------------- hero */}
      <section className="max-w-6xl mx-auto px-5 pt-14 pb-12 sm:pt-20 sm:pb-16 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <h1 className="text-[2rem] sm:text-5xl font-semibold tracking-[-.025em] leading-[1.08]">
            {hero.headline}
          </h1>
          <p className="mt-5 text-lg text-slate-600 leading-relaxed max-w-xl">{hero.subheadline}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Cta href={hero.primary_href} icon={ArrowRight}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-700 px-6 font-semibold text-white hover:bg-brand-800">
              {hero.primary_label}
            </Cta>
            <Cta href={hero.secondary_href}
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-line px-6 font-medium hover:bg-slate-50">
              {hero.secondary_label}
            </Cta>
          </div>
        </div>
        {heroImg?.src && (
          <div className="rounded-2xl overflow-hidden border border-line shadow-lift">
            <img src={heroImg.src} alt={heroImg.alt_text || ''} className="w-full h-64 sm:h-80 object-cover" />
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------- trust */}
      {B.trust?.items?.length > 0 && (
        <section className="border-y border-line bg-slate-50/70">
          <div className="max-w-6xl mx-auto px-5 py-8 grid grid-cols-2 lg:grid-cols-4 gap-6">
            {B.trust.items.map((t, i) => (
              <div key={i}>
                <p className="text-lg font-semibold tracking-[-.01em]">{t.value}</p>
                <p className="text-sm text-slate-600 mt-0.5">{t.label}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* -------------------------------------------------------- problem */}
      {B.problem?.items?.length > 0 && (
        <section className="max-w-6xl mx-auto px-5 py-16">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.problem.title}</h2>
          {B.problem.intro && <p className="mt-3 text-slate-600 max-w-2xl">{B.problem.intro}</p>}
          <div className="mt-8 grid sm:grid-cols-2 gap-4">
            {B.problem.items.map((it, i) => (
              <div key={i} className="rounded-xl border border-line p-5">
                <p className="text-sm text-slate-500 line-through decoration-slate-300">{it.before}</p>
                <p className="mt-2 font-medium flex gap-2"><Check size={17} className="text-emerald-600 mt-0.5 shrink-0" />{it.after}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------- features */}
      {B.features?.items?.length > 0 && (
        <section id="features" className="bg-slate-50/70 border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-16">
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.features.title}</h2>
            <div className="mt-9 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {B.features.items.map((f, i) => {
                const Icon = ICONS[f.icon] || BedDouble
                return (
                  <div key={i} className="rounded-xl border border-line bg-white p-5">
                    <span className="h-10 w-10 rounded-lg bg-brand-50 text-brand-700 inline-flex items-center justify-center">
                      <Icon size={19} />
                    </span>
                    <h3 className="mt-4 font-semibold">{f.title}</h3>
                    <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{f.text}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}

      {/* ---------------------------------------------------- screenshots */}
      {B.screenshots?.items?.some((s) => img(s.image_slot)?.src) && (
        <section className="max-w-6xl mx-auto px-5 py-16">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.screenshots.title}</h2>
          <div className="mt-8 grid sm:grid-cols-2 gap-5">
            {B.screenshots.items.filter((s) => img(s.image_slot)?.src).map((s, i) => (
              <figure key={i} className="rounded-xl overflow-hidden border border-line bg-white">
                <img src={img(s.image_slot).src} alt={img(s.image_slot).alt_text || s.caption || ''}
                  className="w-full h-auto" loading="lazy" />
                {s.caption && <figcaption className="px-4 py-2.5 text-sm text-slate-600 border-t border-line">{s.caption}</figcaption>}
              </figure>
            ))}
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------ how */}
      {B.how?.steps?.length > 0 && (
        <section className="bg-slate-50/70 border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-16">
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.how.title}</h2>
            <ol className="mt-9 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {B.how.steps.map((s, i) => (
                <li key={i} className="rounded-xl bg-white border border-line p-5">
                  <span className="h-7 w-7 rounded-full bg-brand-700 text-white text-sm font-semibold inline-flex items-center justify-center">{i + 1}</span>
                  <h3 className="mt-3.5 font-semibold">{s.title}</h3>
                  <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      )}

      {/* -------------------------------------------------------- pricing */}
      {B.pricing && (
        <section id="pricing" className="max-w-6xl mx-auto px-5 py-16">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.pricing.title}</h2>
          {B.pricing.intro && <p className="mt-3 text-slate-600 max-w-2xl">{B.pricing.intro}</p>}
          <div className="mt-9 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {PLANS.filter((p) => p.active).map((p) => (
              <div key={p.id}
                className={`rounded-xl border p-5 flex flex-col ${p.popular ? 'border-brand-400 ring-1 ring-brand-200' : 'border-line'}`}>
                {p.popular && <span className="self-start text-2xs font-semibold bg-brand-700 text-white rounded-full px-2.5 py-0.5 mb-2">Most chosen</span>}
                <h3 className="font-semibold">{p.name}</h3>
                <p className="mt-2 text-2xl font-semibold tnum">{rupees(p.price)}
                  <span className="text-sm font-normal text-slate-500">/{p.cycle}</span></p>
                <p className="mt-1 text-xs text-slate-500 tnum">
                  {p.limits.beds} beds · {p.limits.branches} branch{p.limits.branches === 1 ? '' : 'es'}
                </p>
                <ul className="mt-4 space-y-1.5 flex-1">
                  {p.features.map((f) => (
                    <li key={f} className="text-sm text-slate-600 flex gap-2">
                      <Check size={15} className="text-emerald-600 mt-0.5 shrink-0" />{f}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Cta href={B.pricing.cta_href} icon={ArrowRight}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-brand-700 px-6 font-semibold text-white hover:bg-brand-800">
              {B.pricing.cta_label}
            </Cta>
            {B.pricing.note && <p className="text-xs text-slate-500">{B.pricing.note}</p>}
          </div>
        </section>
      )}

      {/* --------------------------------------------------- testimonials */}
      {B.testimonials?.items?.length > 0 && (
        <section className="bg-slate-50/70 border-y border-line">
          <div className="max-w-6xl mx-auto px-5 py-16">
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.testimonials.title}</h2>
            <div className="mt-8 grid sm:grid-cols-3 gap-4">
              {B.testimonials.items.map((t, i) => (
                <figure key={i} className="rounded-xl bg-white border border-line p-5">
                  <blockquote className="text-slate-700 leading-relaxed">“{t.quote}”</blockquote>
                  <figcaption className="mt-4 text-sm">
                    <span className="font-medium">{t.name}</span>
                    <span className="block text-slate-500 text-xs">{[t.pg, t.city].filter(Boolean).join(' · ')}</span>
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------ faq */}
      {B.faq?.items?.length > 0 && (
        <section id="faq" className="max-w-6xl mx-auto px-5 py-16">
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.faq.title}</h2>
          <dl className="mt-8 divide-y divide-line border-y border-line">
            {B.faq.items.map((f, i) => (
              <div key={i} className="py-5">
                <dt className="font-medium">{f.q}</dt>
                <dd className="mt-1.5 text-slate-600 leading-relaxed">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* ------------------------------------------------------------ cta */}
      {B.cta && (
        <section className="max-w-6xl mx-auto px-5 pb-16">
          <div className="rounded-2xl bg-brand-700 text-white px-7 py-12 sm:px-12">
            <h2 className="text-2xl sm:text-3xl font-semibold tracking-[-.02em]">{B.cta.headline}</h2>
            <p className="mt-3 text-brand-100 max-w-xl leading-relaxed">{B.cta.text}</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Cta href={B.cta.primary_href} icon={ArrowRight}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-6 font-semibold text-brand-800 hover:bg-brand-50">
                {B.cta.primary_label}
              </Cta>
              <Cta href={B.cta.secondary_href} icon={Download}
                className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/35 px-6 font-medium text-white hover:bg-white/10">
                {B.cta.secondary_label}
              </Cta>
            </div>
          </div>
        </section>
      )}

      {/* -------------------------------------------------------- contact */}
      {B.contact && (
        <section id="contact" className="border-t border-line bg-slate-50/70">
          <div className="max-w-6xl mx-auto px-5 py-14">
            <h2 className="text-2xl font-semibold tracking-[-.02em]">{B.contact.title}</h2>
            <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-4 gap-5 text-sm">
              {B.contact.phone && (
                <a href={`tel:${B.contact.phone}`} className="flex gap-2.5 hover:text-brand-700">
                  <Phone size={17} className="text-slate-400 mt-0.5 shrink-0" />
                  <span><span className="block text-slate-500 text-xs">Phone</span>{B.contact.phone}</span>
                </a>
              )}
              {B.contact.email && (
                <a href={`mailto:${B.contact.email}`} className="flex gap-2.5 hover:text-brand-700">
                  <Mail size={17} className="text-slate-400 mt-0.5 shrink-0" />
                  <span><span className="block text-slate-500 text-xs">Email</span>{B.contact.email}</span>
                </a>
              )}
              {B.contact.address && (
                <p className="flex gap-2.5">
                  <MapPin size={17} className="text-slate-400 mt-0.5 shrink-0" />
                  <span><span className="block text-slate-500 text-xs">Address</span>{B.contact.address}</span>
                </p>
              )}
              {B.contact.hours && (
                <p className="flex gap-2.5">
                  <Clock size={17} className="text-slate-400 mt-0.5 shrink-0" />
                  <span><span className="block text-slate-500 text-xs">Hours</span>{B.contact.hours}</span>
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* --------------------------------------------------------- footer */}
      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-5 py-8 flex flex-col sm:flex-row gap-4 sm:items-center text-sm text-slate-500">
          <p>
            {B.footer?.copyright || `© ${new Date().getFullYear()} ${B.footer?.legal_name || brand.name || ''}`.trim()}
            {brand.show_company && brand.company && (
              <> · built by {brand.company_url
                ? <a href={brand.company_url} className="hover:text-slate-800">{brand.company}</a>
                : brand.company}</>
            )}
          </p>
          <nav className="sm:ml-auto flex flex-wrap gap-5">
            {(B.footer?.links || []).map((l) => (
              <Cta key={l.href} href={l.href} className="hover:text-slate-800">{l.label}</Cta>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  )
}
