/**
 * Photos on a branch's public listing: up to six, each under 5 KB.
 *
 * Built to feel identical to adding a resident's Aadhaar scan, because an owner
 * who has done that once already knows this. Same two doors, same crop box, same
 * "under 5 KB" confirmation before anything is saved:
 *
 *   Take photo   - the phone's own camera opens (a plain file input with
 *                  `capture`, which the Android app already supports, so no new
 *                  APK is needed). The picture is cropped and shrunk on the
 *                  device; the full-size original never leaves it.
 *   Upload image - taken exactly as it is, but only if it is already under
 *                  5 KB. A bigger file is refused with its real size, and the
 *                  owner can then have it shrunk the same way as a camera shot.
 *
 * The one difference from ResidentDocuments is that these are published. So the
 * screen says so, out loud, above the grid - an owner should never discover
 * afterwards that a photo of their own front door is on the internet.
 *
 * The first photo is the only one a seeker sees on a search card, so it can be
 * moved to the front. That is a selling decision and belongs to the owner.
 */
import { useEffect, useRef, useState } from 'react'
import {
  Camera, Upload, Trash2, Plus, RotateCcw, CheckCircle2, Minimize2, Star, ImageIcon,
} from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { branchApi } from '@/services/api/branchApi'
import { useToast } from '@/context/ToastContext'
import { Button, Modal, FormField, Input, InlineAlert, Skeleton } from '@/components/ui'
import {
  PHOTO_MAX_BYTES, PHOTOS_PER_BRANCH, photoSizeLabel,
  compressPhoto, acceptSmallPhoto,
} from '@/lib/photoScan'

const cx = (...a) => a.filter(Boolean).join(' ')
const clamp = (v, a, b) => Math.min(b, Math.max(a, v))
const START_BOX = { x: 0.04, y: 0.10, w: 0.92, h: 0.70 }

/* ------------------------------------------------------------------ crop */
function CropBox({ src, box, onChange }) {
  const ref = useRef(null)
  const drag = useRef(null)
  const [portrait, setPortrait] = useState(false)

  const begin = (mode) => (e) => {
    e.preventDefault(); e.stopPropagation()
    drag.current = { mode, x: e.clientX, y: e.clientY, box }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const move = (e) => {
    const d = drag.current
    if (!d || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const dx = (e.clientX - d.x) / r.width
    const dy = (e.clientY - d.y) / r.height
    let { x, y, w, h } = d.box
    const min = 0.15
    if (d.mode === 'move') {
      x = clamp(x + dx, 0, 1 - w); y = clamp(y + dy, 0, 1 - h)
    } else {
      if (d.mode.includes('l')) { const nx = clamp(x + dx, 0, x + w - min); w += x - nx; x = nx }
      if (d.mode.includes('r')) w = clamp(w + dx, min, 1 - x)
      if (d.mode.includes('t')) { const ny = clamp(y + dy, 0, y + h - min); h += y - ny; y = ny }
      if (d.mode.includes('b')) h = clamp(h + dy, min, 1 - y)
    }
    onChange({ x, y, w, h })
  }
  const end = () => { drag.current = null }
  const handle = 'absolute h-6 w-6 -m-3 rounded-full bg-white border-2 border-brand-600 shadow touch-none'

  return (
    <div className="flex justify-center">
      <div ref={ref} className="relative select-none touch-none"
        style={{ width: portrait ? '72%' : '100%' }}
        onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
        <img src={src} alt="Your photo" draggable={false} className="block w-full h-auto rounded-md"
          onLoad={(e) => setPortrait(e.currentTarget.naturalHeight > e.currentTarget.naturalWidth)} />
        <div className="absolute border-2 border-white cursor-move touch-none shadow-[0_0_0_9999px_rgba(15,23,42,0.55)]"
          style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.w * 100}%`, height: `${box.h * 100}%` }}
          onPointerDown={begin('move')}>
          <span className={cx(handle, 'left-0 top-0 cursor-nwse-resize')} onPointerDown={begin('tl')} />
          <span className={cx(handle, 'right-0 top-0 cursor-nesw-resize')} onPointerDown={begin('tr')} />
          <span className={cx(handle, 'left-0 bottom-0 cursor-nesw-resize')} onPointerDown={begin('bl')} />
          <span className={cx(handle, 'right-0 bottom-0 cursor-nwse-resize')} onPointerDown={begin('br')} />
        </div>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- capture */
export function PhotoCapture({ open, onClose, onDone }) {
  const [caption, setCaption] = useState('')
  const [file, setFile] = useState(null)
  const [src, setSrc] = useState(null)
  const [box, setBox] = useState(START_BOX)
  const [origin, setOrigin] = useState('camera')
  const [result, setResult] = useState(null)
  const [problem, setProblem] = useState(null)
  const [busy, setBusy] = useState(false)
  const cameraRef = useRef(null)
  const uploadRef = useRef(null)

  useEffect(() => {
    if (!open) return
    setCaption(''); setFile(null); setSrc(null); setBox(START_BOX)
    setResult(null); setProblem(null); setBusy(false)
  }, [open])
  useEffect(() => () => { if (src) URL.revokeObjectURL(src) }, [src])

  const startCrop = (f, from) => {
    setOrigin(from); setFile(f); setSrc(URL.createObjectURL(f)); setBox(START_BOX)
    setResult(null); setProblem(null)
  }
  const onCamera = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (f) startCrop(f, 'camera')
  }
  const onUpload = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setFile(null); setSrc(null); setResult(null); setProblem(null)
    try {
      setOrigin('upload')
      setResult(await acceptSmallPhoto(f))
    } catch (err) {
      setProblem({ message: err.message, tooLarge: !!err.tooLarge, file: f })
    }
  }
  const shrink = async () => {
    setBusy(true)
    try {
      setResult(await compressPhoto(file, { crop: box }))
      setProblem(null)
    } catch (err) { setProblem({ message: err.message }) }
    finally { setBusy(false) }
  }
  const retake = () => { setFile(null); setSrc(null); setResult(null); setProblem(null) }
  const save = () => onDone({
    caption: caption.trim() || null, image: result.dataUrl, dataUrl: result.dataUrl,
    size: result.size, width: result.width || null, height: result.height || null,
    source: origin,
  })

  const cropping = file && !result
  return (
    <Modal open={open} onClose={onClose} size="md" title="Add a photo"
      subtitle="A room, the building or the mess. Stored under 5 KB and shown publicly."
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        {cropping && (
          <Button variant="primary" icon={Minimize2} loading={busy} onClick={shrink}>
            Make it under 5 KB
          </Button>
        )}
        {result && <Button variant="primary" icon={CheckCircle2} onClick={save}>Save photo</Button>}
      </>}>
      <div className="space-y-4">
        <FormField label="Caption" hint="Optional. Shown under the photo.">
          <Input value={caption} maxLength={80} placeholder="Two-sharing room, east facing"
            onChange={(e) => setCaption(e.target.value)} />
        </FormField>

        <input ref={cameraRef} type="file" accept="image/*" capture="environment"
          className="hidden" onChange={onCamera} />
        <input ref={uploadRef} type="file" accept="image/jpeg,image/png,image/webp"
          className="hidden" onChange={onUpload} />

        {!file && !result && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" onClick={() => cameraRef.current?.click()}
                className="rounded-xl border-2 border-brand-200 bg-brand-50 hover:bg-brand-100 p-4 flex flex-col items-center gap-2 text-brand-800">
                <Camera size={24} /><span className="text-sm font-semibold">Take photo</span>
                <span className="text-2xs text-brand-700/80">Shrunk to under 5 KB for you</span>
              </button>
              <button type="button" onClick={() => uploadRef.current?.click()}
                className="rounded-xl border-2 border-line bg-white hover:bg-slate-50 p-4 flex flex-col items-center gap-2 text-slate-700">
                <Upload size={24} /><span className="text-sm font-semibold">Upload image</span>
                <span className="text-2xs text-slate-500">Must be under 5 KB</span>
              </button>
            </div>
            {problem && (
              <InlineAlert tone="error" title={problem.tooLarge ? 'Photos must be under 5 KB' : 'That did not work'}>
                {problem.message}
                {problem.tooLarge && (
                  <div className="mt-2">
                    <Button size="sm" icon={Minimize2} onClick={() => startCrop(problem.file, 'upload')}>
                      Shrink it to under 5 KB</Button>
                  </div>
                )}
              </InlineAlert>
            )}
          </>
        )}

        {cropping && (
          <>
            <CropBox src={src} box={box} onChange={setBox} />
            <p className="text-xs text-slate-500 text-center">
              Drag the corners to frame the shot. At 5 KB a tight frame on one good
              thing beats a wide shot of everything.
            </p>
            {problem && <InlineAlert tone="error">{problem.message}</InlineAlert>}
          </>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-xl border border-line bg-slate-50 p-3 flex justify-center">
              <img src={result.dataUrl} alt="Saved copy" className="max-w-full h-auto rounded" />
            </div>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-emerald-700 inline-flex items-center gap-1.5">
                <CheckCircle2 size={16} /> {photoSizeLabel(result.size)}
                {result.width ? ` · ${result.width}×${result.height}` : ''} · under 5 KB
              </p>
              <Button size="sm" icon={RotateCcw} onClick={retake}>Retake</Button>
            </div>
            <p className="text-2xs text-slate-500">
              This is exactly what people searching will see. Save it only if it looks right.
            </p>
          </div>
        )}
      </div>
    </Modal>
  )
}

/* ------------------------------------------------------------------ grid */
export function BranchPhotos({ branchId, canEdit = true, onChanged }) {
  const { success, error } = useToast()
  const photos = useApi(() => (branchId ? branchApi.photos(branchId) : Promise.resolve(null)),
    [branchId])
  const [capturing, setCapturing] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const items = photos.data?.items || []
  const free = Math.max(0, PHOTOS_PER_BRANCH - items.length)

  const add = async (photo) => {
    setCapturing(false)
    try {
      await branchApi.addPhoto(branchId, {
        image: photo.image, caption: photo.caption,
        source: photo.source, width: photo.width, height: photo.height,
      })
      success('Photo added', `${photoSizeLabel(photo.size)}, now on your listing.`)
      photos.reload()
      onChanged?.()
    } catch (err) { error('Could not save the photo', err.message) }
  }

  const remove = async (p) => {
    setBusyId(p.id)
    try {
      await branchApi.deletePhoto(branchId, p.id)
      success('Photo deleted')
      photos.reload()
      onChanged?.()
    } catch (err) { error('Could not delete it', err.message) }
    finally { setBusyId(null) }
  }

  const makeLead = async (p) => {
    setBusyId(p.id)
    try {
      await branchApi.reorderPhotos(branchId, [p.id, ...items.filter((x) => x.id !== p.id).map((x) => x.id)])
      success('Moved to the front', 'This is the photo people see first.')
      photos.reload()
    } catch (err) { error('Could not reorder', err.message) }
    finally { setBusyId(null) }
  }

  if (!branchId) {
    return (
      <InlineAlert tone="info">
        Save the branch first, then photos can be added to it.
      </InlineAlert>
    )
  }
  if (photos.loading && !photos.data) return <Skeleton className="h-36" />
  if (photos.error) return <InlineAlert tone="error">{photos.error.message}</InlineAlert>

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {items.map((p, index) => (
          <div key={p.id} className="rounded-xl border border-line bg-white overflow-hidden">
            <div className="relative">
              <button type="button" onClick={() => setViewing(p)}
                className="block w-full bg-slate-100">
                <img src={p.data_url} alt={p.caption || 'Listing photo'}
                  className="w-full h-28 object-cover" />
              </button>
              {index === 0 && (
                <span className="absolute top-1.5 left-1.5 inline-flex items-center gap-1 rounded-full bg-brand-700 text-white text-2xs px-2 py-0.5">
                  <Star size={10} /> Shown first
                </span>
              )}
            </div>
            <div className="p-2.5 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">
                  {p.caption || `Photo ${index + 1}`}
                </p>
                <p className="text-2xs text-slate-500 truncate">
                  {[photoSizeLabel(p.size_bytes), p.source === 'upload' ? 'uploaded' : 'camera']
                    .join(' · ')}
                </p>
              </div>
              {canEdit && (
                <div className="flex shrink-0">
                  {index !== 0 && (
                    <button type="button" onClick={() => makeLead(p)} disabled={busyId === p.id}
                      aria-label="Show this photo first"
                      className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-brand-700 hover:bg-brand-50 disabled:opacity-50">
                      <Star size={15} />
                    </button>
                  )}
                  <button type="button" onClick={() => remove(p)} disabled={busyId === p.id}
                    aria-label="Delete this photo"
                    className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 disabled:opacity-50">
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        {canEdit && Array.from({ length: free }).map((_, i) => (
          <button key={`slot-${i}`} type="button" onClick={() => setCapturing(true)}
            className="h-[10.5rem] rounded-xl border-2 border-dashed border-line hover:border-brand-300 hover:bg-brand-50/40 flex flex-col items-center justify-center gap-1.5 text-slate-500 hover:text-brand-700 transition-colors">
            <Plus size={20} />
            <span className="text-sm font-medium">Add photo</span>
            <span className="text-2xs">Camera or upload</span>
          </button>
        ))}
      </div>

      <p className="text-2xs text-slate-500 mt-2">
        Up to {PHOTOS_PER_BRANCH} photos, each stored under {PHOTO_MAX_BYTES / 1024} KB.
        The first one is what people see in search results.
      </p>

      <PhotoCapture open={capturing} onClose={() => setCapturing(false)} onDone={add} />

      <Modal open={!!viewing} onClose={() => setViewing(null)} size="md"
        title={viewing?.caption || 'Listing photo'}
        subtitle={viewing ? photoSizeLabel(viewing.size_bytes) : ''}>
        {viewing?.data_url && (
          <div className="flex justify-center bg-slate-50 rounded-lg p-2">
            <img src={viewing.data_url} alt={viewing.caption || 'Listing photo'}
              className="w-full h-auto max-w-lg rounded" />
          </div>
        )}
      </Modal>
    </div>
  )
}

/** Small inline summary for screens that only need "are there photos?". */
export function PhotoSummary({ count = 0 }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <ImageIcon size={13} className="text-slate-400" />
      {count === 0 ? 'No photos yet' : `${count} photo${count === 1 ? '' : 's'}`}
    </span>
  )
}
