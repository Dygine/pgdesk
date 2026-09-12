/**
 * Master -> Website. Editing the public site without touching code.
 *
 * Every section of pgguru.in is a row in `site_blocks`, and this is where those
 * rows get written. A block nobody has edited renders from a preset held on the
 * server, so the site is complete before anyone touches this screen - and
 * "Reset" here means deleting the row and going back to that preset, not
 * restoring some remembered copy.
 *
 * Why the fields are generated rather than hand-written
 * -----------------------------------------------------
 * The block bodies are JSON whose shape differs per section and changes as the
 * page does. Hand-writing a form per section would mean editing this file every
 * time the marketing page grows a field - exactly the friction the whole
 * feature exists to remove. So the editor walks the block body and renders a
 * control per value: a text box for a string, a switch for a boolean, a
 * repeating group for a list of objects. Add a field to a preset on the server
 * and it appears here on the next load, with no change to this file.
 *
 * The trade is that it is a generic editor rather than a bespoke one, which is
 * the right trade for a page edited a few times a month by the person who owns
 * it.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Globe, Save, RotateCcw, Eye, EyeOff, Image as ImageIcon, Link2, Upload,
  Trash2, Plus, ExternalLink, AlertTriangle,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { siteApi } from '@/services/api/siteApi'
import { useToast } from '@/context/ToastContext'
import { PageHeader } from '@/components/domain'
import {
  Card, Button, Input, Textarea, FormField, Toggle, InlineAlert, Skeleton, Modal,
  StatusBadge,
} from '@/components/ui'
import { compressPhoto, acceptSmallPhoto, photoSizeLabel } from '@/lib/photoScan'

const LABELS = {
  brand: 'Brand', hero: 'Hero', trust: 'Trust strip', problem: 'What it replaces',
  features: 'Features', screenshots: 'Screenshots', how: 'How it works',
  pricing: 'Pricing', testimonials: 'Testimonials', faq: 'Questions',
  cta: 'Closing call to action', contact: 'Contact', footer: 'Footer',
  seo: 'Search engines',
}

/** Fields whose names say they want more than one line. */
const LONG = /(text|description|intro|subheadline|a|quote|address|note|keywords)$/i
const titleise = (k) => k.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

/* ------------------------------------------------------------------ fields */
function Field({ name, value, onChange }) {
  if (typeof value === 'boolean') {
    return (
      <div className="rounded-lg border border-line px-3 sm:col-span-2">
        <Toggle checked={value} onChange={onChange} label={titleise(name)} />
      </div>
    )
  }
  const long = LONG.test(name) || String(value ?? '').length > 90
  return (
    <FormField label={titleise(name)} className={long ? 'sm:col-span-2' : ''}>
      {long
        ? <Textarea rows={3} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
        : <Input value={value ?? ''} onChange={(e) => onChange(e.target.value)} />}
    </FormField>
  )
}

/** A list of objects - features, FAQ entries, testimonials. */
function Repeater({ name, items, onChange }) {
  const shape = items[0] || {}
  const blank = Object.fromEntries(Object.keys(shape).map((k) => [k, '']))
  const set = (i, key, v) =>
    onChange(items.map((it, idx) => (idx === i ? { ...it, [key]: v } : it)))

  return (
    <div className="sm:col-span-2">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[13px] font-medium text-slate-700">{titleise(name)}</p>
        <Button size="sm" icon={Plus}
          onClick={() => onChange([...items, Object.keys(blank).length ? blank : { title: '', text: '' }])}>
          Add
        </Button>
      </div>
      <div className="space-y-3">
        {items.map((item, i) => (
          <div key={i} className="rounded-lg border border-line p-3">
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-2xs text-slate-400 tnum">#{i + 1}</span>
              <button type="button" aria-label={`Remove item ${i + 1}`}
                onClick={() => onChange(items.filter((_, idx) => idx !== i))}
                className="h-7 w-7 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50">
                <Trash2 size={14} />
              </button>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              {Object.entries(item).map(([k, v]) => (
                <Field key={k} name={k} value={v} onChange={(nv) => set(i, k, nv)} />
              ))}
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-slate-500 py-3">
            Nothing here yet. This section stays off the website until you add something.
          </p>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- block */
function BlockEditor({ block, onSaved }) {
  const { success, error } = useToast()
  const [body, setBody] = useState(block.body)
  const [live, setLive] = useState(block.is_published)
  const [busy, setBusy] = useState(false)

  useEffect(() => { setBody(block.body); setLive(block.is_published) }, [block])

  const dirty = useMemo(
    () => JSON.stringify(body) !== JSON.stringify(block.body) || live !== block.is_published,
    [body, live, block])

  const set = (k, v) => setBody((b) => ({ ...b, [k]: v }))

  const save = async () => {
    setBusy(true)
    try {
      await siteApi.saveBlock(block.key, body, live)
      success('Saved', 'The website shows this on its next load.')
      onSaved()
    } catch (err) { error('Could not save', err.message) } finally { setBusy(false) }
  }

  const reset = async () => {
    setBusy(true)
    try {
      await siteApi.resetBlock(block.key)
      success('Reset to the original wording')
      onSaved()
    } catch (err) { error('Could not reset', err.message) } finally { setBusy(false) }
  }

  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2.5 mb-4">
        <h2 className="font-semibold">{LABELS[block.key] || titleise(block.key)}</h2>
        {block.customised
          ? <StatusBadge status="Edited" tone="brand" />
          : <StatusBadge status="Original" tone="slate" />}
        {!live && <StatusBadge status="Hidden" tone="amber" dot />}
        <div className="ml-auto flex gap-2">
          <Button size="sm" icon={live ? Eye : EyeOff} onClick={() => setLive(!live)}>
            {live ? 'Showing' : 'Hidden'}
          </Button>
          {block.customised && (
            <Button size="sm" icon={RotateCcw} onClick={reset} disabled={busy}>Reset</Button>
          )}
          <Button size="sm" variant="primary" icon={Save} loading={busy}
            disabled={!dirty} onClick={save}>Save</Button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        {Object.entries(body).map(([k, v]) => {
          if (Array.isArray(v)) {
            return <Repeater key={k} name={k} items={v} onChange={(nv) => set(k, nv)} />
          }
          if (v !== null && typeof v === 'object') return null   // nothing nests today
          return <Field key={k} name={k} value={v} onChange={(nv) => set(k, nv)} />
        })}
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ images */
function ImageManager({ images, maxBytes, onChanged }) {
  const { success, error } = useToast()
  const [editing, setEditing] = useState(null)   // { slot, mode }
  const [slot, setSlot] = useState('')
  const [url, setUrl] = useState('')
  const [alt, setAlt] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState(null)

  const open = (existing) => {
    setEditing(existing || { slot: '', new: true })
    setSlot(existing?.slot || '')
    setUrl(existing?.hosted ? existing.src : '')
    setAlt(existing?.alt_text || '')
    setFile(null); setProblem(null)
  }

  const pick = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setProblem(null)
    try {
      // Website images get a far bigger budget than a 5 KB listing photo - a
      // hero shot at 5 KB looks like a mistake. Anything already small enough
      // is taken as-is; anything larger is shrunk to fit.
      setFile(f.size <= maxBytes
        ? await acceptSmallPhoto(f).catch(() => null) || await compressPhoto(f, { limit: maxBytes })
        : await compressPhoto(f, { limit: maxBytes }))
    } catch (err) { setProblem(err.message) }
  }

  const save = async () => {
    const name = slot.trim()
    if (!name) return setProblem('Give the image a slot name, such as "hero".')
    if (!url.trim() && !file) return setProblem('Paste a link, or choose a file.')
    setBusy(true)
    try {
      await siteApi.saveImage({
        slot: name, alt_text: alt.trim(),
        ...(file ? { image: file.dataUrl } : { url: url.trim() }),
      })
      success('Image saved')
      setEditing(null)
      onChanged()
    } catch (err) { error('Could not save the image', err.message) } finally { setBusy(false) }
  }

  const remove = async (s) => {
    try {
      await siteApi.deleteImage(s)
      success('Image removed')
      onChanged()
    } catch (err) { error('Could not remove it', err.message) }
  }

  const rows = Object.values(images)

  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-center gap-2.5 mb-1">
        <h2 className="font-semibold">Images</h2>
        <Button size="sm" icon={Plus} className="ml-auto" onClick={() => open(null)}>Add image</Button>
      </div>
      <p className="text-sm text-slate-500 mb-4">
        Each image has a <b>slot</b> name. Sections point at a slot, so swapping the
        picture never means editing the section. Use a link for stock photography,
        or upload your own — uploads are shrunk to under {Math.round(maxBytes / 1024)} KB.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {rows.map((im) => (
          <div key={im.slot} className="rounded-xl border border-line overflow-hidden bg-white">
            {im.src
              ? <img src={im.src} alt={im.alt_text || im.slot} className="w-full h-24 object-cover bg-slate-100" />
              : <div className="w-full h-24 bg-slate-50 flex items-center justify-center text-slate-300"><ImageIcon size={20} /></div>}
            <div className="p-2.5">
              <p className="text-xs font-medium truncate">{im.slot}</p>
              <p className="text-2xs text-slate-500 truncate">
                {im.preset ? 'Original' : im.hosted ? 'Linked' : photoSizeLabel(im.size_bytes || 0)}
              </p>
              <div className="flex gap-1 mt-1.5">
                <button type="button" onClick={() => open(im)}
                  className="text-2xs text-brand-700 hover:underline">Change</button>
                {!im.preset && (
                  <button type="button" onClick={() => remove(im.slot)}
                    className="text-2xs text-rose-600 hover:underline ml-auto">Remove</button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal open={!!editing} onClose={() => setEditing(null)} size="sm"
        title={editing?.new ? 'Add an image' : `Change “${editing?.slot}”`}
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>Save image</Button></>}>
        <div className="space-y-4">
          {problem && <InlineAlert tone="error">{problem}</InlineAlert>}
          <FormField label="Slot name" hint="What the section points at, e.g. hero, shot-beds.">
            <Input value={slot} disabled={!editing?.new}
              onChange={(e) => setSlot(e.target.value)} placeholder="hero" />
          </FormField>
          <FormField label="Link to an image"
            hint="Any https:// address. Costs nothing to store and loads from wherever it lives.">
            <Input value={url} onChange={(e) => { setUrl(e.target.value); setFile(null) }}
              placeholder="https://images.unsplash.com/..." />
          </FormField>
          <div className="text-center text-xs text-slate-400">or</div>
          <label className="block rounded-xl border-2 border-dashed border-line hover:border-brand-300 p-4 text-center cursor-pointer">
            <Upload size={20} className="mx-auto text-slate-400" />
            <span className="block text-sm font-medium mt-1.5">Upload a file</span>
            <span className="block text-2xs text-slate-500">
              Shrunk to under {Math.round(maxBytes / 1024)} KB
            </span>
            <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={pick} />
          </label>
          {file && (
            <div className="rounded-lg border border-line p-2 flex items-center gap-3">
              <img src={file.dataUrl} alt="" className="h-12 w-16 object-cover rounded" />
              <p className="text-xs text-emerald-700">{photoSizeLabel(file.size)} · ready</p>
            </div>
          )}
          <FormField label="Alt text"
            hint="What the picture shows. Screen readers read this out, and Google reads it too.">
            <Input value={alt} maxLength={160} onChange={(e) => setAlt(e.target.value)} />
          </FormField>
        </div>
      </Modal>
    </Card>
  )
}

/* -------------------------------------------------------------------- page */
export default function MasterWebsite() {
  const site = useApi(() => siteApi.admin(), [])

  if (site.loading && !site.data) {
    return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}</div>
  }
  if (site.error) return <InlineAlert tone="error">{site.error.message}</InlineAlert>

  const { blocks = [], images = {}, max_image_bytes: maxBytes = 120 * 1024 } = site.data || {}

  return (
    <div>
      <PageHeader title="Website" icon={Globe}
        subtitle="Everything on the public site. Edits are live on the next page load — there is nothing to deploy."
        actions={<a href="/" target="_blank" rel="noreferrer">
          <Button icon={ExternalLink}>View the site</Button>
        </a>} />

      <InlineAlert tone="warn" className="mb-4" title="Only claim what is true">
        Testimonials and any numbers on the trust strip go on a public page in your
        company's name. Leave a section hidden until you have something real to put
        in it — an invented review is the kind of thing that is cheap to write and
        expensive to answer for.
      </InlineAlert>

      <div className="space-y-4">
        <ImageManager images={images} maxBytes={maxBytes} onChanged={site.reload} />
        {blocks.map((b) => (
          <BlockEditor key={b.key} block={b} onSaved={site.reload} />
        ))}
      </div>
    </div>
  )
}
