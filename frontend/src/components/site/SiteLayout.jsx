/**
 * The frame every marketing page sits in: header, footer, and the content.
 *
 * One fetch, shared. The site is now several pages (/, /features, /pricing,
 * /faq, /contact) and each one needs the same blocks, so the content is fetched
 * once here and handed down through an outlet context. Navigating between pages
 * is instant and makes no request.
 *
 * Presets are bundled, so the page renders complete before - and without - any
 * API answer. See src/data/sitePresets.js for why that matters.
 */
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Menu, X, Search, ArrowRight } from 'lucide-react'
import { siteApi } from '@/services/api/siteApi'
import { SITE_PRESETS, SITE_PRESET_IMAGES } from '@/data/sitePresets'

const SiteCtx = createContext(null)
export const useSite = () => useContext(SiteCtx)

const merge = (api) => {
  const blocks = { ...SITE_PRESETS }
  Object.entries(api?.blocks || {}).forEach(([k, v]) => { blocks[k] = { ...blocks[k], ...v } })
  if (api?.blocks) {
    Object.keys(blocks).forEach((k) => { if (!(k in api.blocks)) delete blocks[k] })
  }
  return { blocks, images: { ...SITE_PRESET_IMAGES, ...(api?.images || {}) } }
}

/**
 * Reveal on scroll.
 *
 * One observer for the whole page rather than one per element, and elements are
 * unobserved once they have arrived - an animation that re-runs every time you
 * scroll past is a tic, not a flourish.
 */
export function useReveal(deps = []) {
  const root = useRef(null)
  useEffect(() => {
    const host = root.current
    if (!host) return undefined
    const targets = host.querySelectorAll('.reveal')
    if (!('IntersectionObserver' in window)) {
      targets.forEach((t) => t.classList.add('in'))
      return undefined
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) }
      })
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 })
    targets.forEach((t) => io.observe(t))
    return () => io.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return root
}

/** Section heading used on every page, so the rhythm is identical throughout. */
export function SectionHead({ eyebrow, title, intro, center }) {
  return (
    <div className={`reveal ${center ? 'text-center max-w-2xl mx-auto' : 'max-w-2xl'}`}>
      {eyebrow && (
        <p className="text-xs font-semibold uppercase tracking-[.14em] text-accent-600 mb-2.5">
          {eyebrow}
        </p>
      )}
      <h2 className="text-2xl sm:text-[2rem] font-semibold tracking-[-.025em] leading-tight">
        {title}
      </h2>
      {intro && <p className="mt-3.5 text-slate-600 leading-relaxed">{intro}</p>}
    </div>
  )
}

/** Internal links route; .apk and external links are plain anchors. */
export function Cta({ href, children, className, icon: Icon }) {
  if (!href) return null
  const inner = <>{children}{Icon ? <Icon size={16} /> : null}</>
  return href.startsWith('/') && !href.endsWith('.apk')
    ? <Link to={href} className={className}>{inner}</Link>
    : <a href={href} className={className}>{inner}</a>
}

export const BTN_PRIMARY =
  'inline-flex h-11 items-center gap-2 rounded-xl bg-brand-600 px-6 font-semibold text-white '
  + 'shadow-lift hover:bg-brand-700 hover:shadow-pop transition-all duration-200 active:translate-y-px'
export const BTN_GHOST =
  'inline-flex h-11 items-center gap-2 rounded-xl border border-line bg-white px-6 font-medium '
  + 'text-slate-700 hover:border-brand-300 hover:bg-brand-50/50 transition-all duration-200'
export const BTN_GOLD =
  'inline-flex h-11 items-center gap-2 rounded-xl bg-accent-400 px-6 font-semibold text-brand-950 '
  + 'shadow-lift hover:bg-accent-300 hover:shadow-pop transition-all duration-200 active:translate-y-px'

const NAV = [
  ['/features', 'Features'],
  ['/pricing', 'Pricing'],
  ['/faq', 'Questions'],
  ['/contact', 'Contact'],
]

export default function SiteLayout() {
  const [site, setSite] = useState(() => merge(null))
  const [menu, setMenu] = useState(false)
  const { pathname } = useLocation()

  useEffect(() => {
    let dead = false
    ;(async () => {
      try {
        const data = await siteApi.content()
        if (!dead) setSite(merge(data))
      } catch { /* presets are already on screen */ }
    })()
    return () => { dead = true }
  }, [])

  useEffect(() => { setMenu(false); window.scrollTo(0, 0) }, [pathname])

  const B = site.blocks
  const brand = B.brand || {}
  const logo = site.images[brand.logo_slot]

  /* Head tags from the `seo` block, per page. */
  useEffect(() => {
    const seo = B.seo
    if (!seo) return
    const page = NAV.find(([to]) => to === pathname)?.[1]
    document.title = page ? `${page} — ${brand.name || 'PGuru'}` : seo.title
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
    meta('theme-color', '#373DA6')
    meta('og:title', document.title, 'property')
    meta('og:description', seo.description, 'property')
    meta('og:type', 'website', 'property')
    const social = site.images[seo.social_image_slot]?.src
    if (social) meta('og:image', social, 'property')
    let link = document.head.querySelector('link[rel="canonical"]')
    if (!link) {
      link = document.createElement('link')
      link.setAttribute('rel', 'canonical')
      document.head.appendChild(link)
    }
    link.setAttribute('href', (seo.canonical || 'https://pgguru.in/').replace(/\/$/, '') + pathname)
  }, [B, site.images, pathname, brand.name])

  return (
    <SiteCtx.Provider value={site}>
      <div className="min-h-dvh bg-white text-slate-900 flex flex-col">

        <header className="sticky top-0 z-30 bg-white/90 backdrop-blur-md border-b border-line safe-t">
          <div className="max-w-6xl mx-auto px-5 h-16 flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2.5 min-w-0 group">
              {logo?.src
                ? <img src={logo.src} alt={brand.name || 'Logo'} className="h-9 w-auto" />
                : <span className="h-9 w-9 rounded-xl bg-brand-600 text-white inline-flex items-center justify-center font-bold">
                    {(brand.name || 'P')[0]}
                  </span>}
            </Link>

            <nav className="hidden md:flex items-center gap-7 ml-7 text-sm">
              {NAV.map(([to, label]) => (
                <NavLink key={to} to={to}
                  className={({ isActive }) => `nav-link font-medium transition-colors ${
                    isActive ? 'text-brand-700' : 'text-slate-600 hover:text-slate-900'}`}>
                  {label}
                </NavLink>
              ))}
            </nav>

            <div className="ml-auto flex items-center gap-2">
              <Link to="/find-pg"
                className="hidden sm:inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3.5 text-sm font-medium hover:border-accent-300 hover:bg-accent-50 transition-colors">
                <Search size={15} className="text-accent-600" /> Find a PG
              </Link>
              <Link to="/login"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white hover:bg-brand-700 transition-colors">
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
            <nav className="md:hidden border-t border-line bg-white px-5 py-4 flex flex-col gap-4 text-sm">
              {NAV.map(([to, label]) => (
                <NavLink key={to} to={to} className="font-medium text-slate-700">{label}</NavLink>
              ))}
              <Link to="/find-pg" className="font-medium text-slate-700">Find a PG</Link>
            </nav>
          )}
        </header>

        <main className="flex-1"><Outlet /></main>

        {/* ------------------------------------------------------- footer */}
        <footer className="bg-brand-950 text-brand-100 mt-auto">
          <div className="max-w-6xl mx-auto px-5 py-14 grid sm:grid-cols-2 lg:grid-cols-4 gap-10">
            <div className="sm:col-span-2 lg:col-span-1">
              <p className="text-white font-semibold text-lg">{brand.name}</p>
              <p className="mt-2.5 text-sm text-brand-200/90 leading-relaxed max-w-xs">
                {brand.tagline}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-accent-300 mb-3.5">Product</p>
              <ul className="space-y-2.5 text-sm">
                {NAV.map(([to, label]) => (
                  <li key={to}><Link to={to} className="hover:text-white transition-colors">{label}</Link></li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-accent-300 mb-3.5">Get started</p>
              <ul className="space-y-2.5 text-sm">
                <li><Link to="/signup" className="hover:text-white transition-colors">Create an account</Link></li>
                <li><Link to="/login" className="hover:text-white transition-colors">Sign in</Link></li>
                <li><Link to="/find-pg" className="hover:text-white transition-colors">Find a PG</Link></li>
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-accent-300 mb-3.5">Contact</p>
              <ul className="space-y-2.5 text-sm">
                {B.contact?.phone && <li><a href={`tel:${B.contact.phone}`} className="hover:text-white">{B.contact.phone}</a></li>}
                {B.contact?.email && <li><a href={`mailto:${B.contact.email}`} className="hover:text-white">{B.contact.email}</a></li>}
                {B.contact?.hours && <li className="text-brand-200/80">{B.contact.hours}</li>}
              </ul>
            </div>
          </div>
          <div className="border-t border-white/10">
            <div className="max-w-6xl mx-auto px-5 py-5 flex flex-col sm:flex-row gap-3 sm:items-center text-xs text-brand-200/80">
              <p>
                {B.footer?.copyright
                  || `© ${new Date().getFullYear()} ${B.footer?.legal_name || brand.name || ''}`.trim()}
                {brand.show_company && brand.company && (
                  <> · built by {brand.company_url
                    ? <a href={brand.company_url} className="hover:text-white underline-offset-2 hover:underline">{brand.company}</a>
                    : brand.company}</>
                )}
              </p>
              <nav className="sm:ml-auto flex flex-wrap gap-5">
                {(B.footer?.links || []).map((l) => (
                  <Cta key={l.href} href={l.href} className="hover:text-white transition-colors">{l.label}</Cta>
                ))}
              </nav>
            </div>
          </div>
        </footer>
      </div>
    </SiteCtx.Provider>
  )
}

export { ArrowRight }
