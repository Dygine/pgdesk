/**
 * Scanned ID documents: up to three per resident, each under 5 KB.
 *
 * Two ways in:
 *   Scan with camera - the phone's own camera opens (a plain file input with
 *     `capture`, which the Android app already supports, so no new APK). The
 *     photo is cropped to the document and shrunk to under 5 KB here.
 *   Upload image - taken exactly as it is, but only if it is already under
 *     5 KB. A bigger file is refused with its size; the person can then choose
 *     to have it shrunk the same way as a scan.
 *
 * Used in two places: the Add resident form (documents are held here and
 * uploaded once the resident exists) and the resident's profile (upload now,
 * or later, and delete).
 */
import { useEffect, useRef, useState } from 'react'
import { Camera, Upload, Trash2, Lock, Plus, RotateCcw, CheckCircle2, Minimize2 } from 'lucide-react'
import { useApi } from '@/lib/useApi'
import { residentApi } from '@/services/api/residentApi'
import { useToast } from '@/context/ToastContext'
import { Button, Modal, FormField, Input, Select, InlineAlert, Skeleton } from '@/components/ui'
import {
  DOC_MAX_BYTES, DOCS_PER_RESIDENT, DOC_TYPES, docTypeLabel, sizeLabel,
  compressDocument, acceptSmallUpload,
} from '@/lib/docScan'

const cx = (...a) => a.filter(Boolean).join(' ')
const clamp = (v, a, b) => Math.min(b, Math.max(a, v))
const START_BOX = { x: 0.06, y: 0.06, w: 0.88, h: 0.88 }

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
    const min = 0.12
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
export function DocumentCapture({ open, onClose, onDone, defaultType = 'AADHAAR' }) {
  const [kind, setKind] = useState(defaultType)
  const [label, setLabel] = useState('')
  const [file, setFile] = useState(null)
  const [src, setSrc] = useState(null)
  const [box, setBox] = useState(START_BOX)
  const [origin, setOrigin] = useState('scan')
  const [result, setResult] = useState(null)
  const [problem, setProblem] = useState(null)
  const [busy, setBusy] = useState(false)
  const cameraRef = useRef(null)
  const uploadRef = useRef(null)

  useEffect(() => {
    if (!open) return
    setKind(defaultType); setLabel(''); setFile(null); setSrc(null); setBox(START_BOX)
    setResult(null); setProblem(null); setBusy(false)
  }, [open, defaultType])
  useEffect(() => () => { if (src) URL.revokeObjectURL(src) }, [src])

  const startCrop = (f, from) => {
    setOrigin(from); setFile(f); setSrc(URL.createObjectURL(f)); setBox(START_BOX)
    setResult(null); setProblem(null)
  }
  const onCamera = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (f) startCrop(f, 'scan')
  }
  const onUpload = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setFile(null); setSrc(null); setResult(null); setProblem(null)
    try {
      setOrigin('upload')
      setResult(await acceptSmallUpload(f))
    } catch (err) {
      setProblem({ message: err.message, tooLarge: !!err.tooLarge, file: f })
    }
  }
  const shrink = async () => {
    setBusy(true)
    try {
      setResult(await compressDocument(file, { crop: box }))
      setProblem(null)
    } catch (err) { setProblem({ message: err.message }) }
    finally { setBusy(false) }
  }
  const retake = () => { setFile(null); setSrc(null); setResult(null); setProblem(null) }
  const save = () => onDone({
    doc_type: kind, label: label.trim() || null, image: result.dataUrl, dataUrl: result.dataUrl,
    size: result.size, width: result.width || null, height: result.height || null, source: origin,
  })

  const cropping = file && !result
  return (
    <Modal open={open} onClose={onClose} size="md" title="Add a document"
      subtitle="Aadhaar, PAN or any government ID. Stored under 5 KB."
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        {cropping && <Button variant="primary" icon={Minimize2} loading={busy} onClick={shrink}>Make it under 5 KB</Button>}
        {result && <Button variant="primary" icon={CheckCircle2} onClick={save}>Save document</Button>}
      </>}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Document">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </FormField>
          <FormField label="Note" hint="Optional">
            <Input value={label} maxLength={60} placeholder="Front side"
              onChange={(e) => setLabel(e.target.value)} />
          </FormField>
        </div>

        <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onCamera} />
        <input ref={uploadRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={onUpload} />

        {!file && !result && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" onClick={() => cameraRef.current?.click()}
                className="rounded-xl border-2 border-brand-200 bg-brand-50 hover:bg-brand-100 p-4 flex flex-col items-center gap-2 text-brand-800">
                <Camera size={24} /><span className="text-sm font-semibold">Scan with camera</span>
                <span className="text-2xs text-brand-700/80">Shrunk to under 5 KB for you</span>
              </button>
              <button type="button" onClick={() => uploadRef.current?.click()}
                className="rounded-xl border-2 border-line bg-white hover:bg-slate-50 p-4 flex flex-col items-center gap-2 text-slate-700">
                <Upload size={24} /><span className="text-sm font-semibold">Upload image</span>
                <span className="text-2xs text-slate-500">Must be under 5 KB</span>
              </button>
            </div>
            {problem && (
              <InlineAlert tone="error" title={problem.tooLarge ? 'Images must be under 5 KB' : 'That did not work'}>
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
              Drag the corners so only the document is inside the box. The tighter the crop,
              the clearer the text stays at 5 KB.
            </p>
            {problem && <InlineAlert tone="error">{problem.message}</InlineAlert>}
          </>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-xl border border-line bg-slate-50 p-3 flex justify-center">
              <img src={result.dataUrl} alt="Saved copy" className="max-w-full h-auto rounded"
                style={{ imageRendering: 'auto' }} />
            </div>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-emerald-700 inline-flex items-center gap-1.5">
                <CheckCircle2 size={16} /> {sizeLabel(result.size)}
                {result.width ? ` · ${result.width}×${result.height}` : ''} · under 5 KB
              </p>
              <Button size="sm" icon={RotateCcw} onClick={retake}>Retake</Button>
            </div>
            <p className="text-2xs text-slate-500">Check the name and ID number are readable before saving.</p>
          </div>
        )}
      </div>
    </Modal>
  )
}

/* ----------------------------------------------------------------- slots */
export function ResidentDocuments({ residentId, pending, onPendingChange, canEdit = true }) {
  const { success, error } = useToast()
  const saved = useApi(() => (residentId ? residentApi.documents(residentId) : Promise.resolve(null)),
    [residentId])
  const [capturing, setCapturing] = useState(false)
  const [viewing, setViewing] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const isPending = !residentId
  const items = isPending ? (pending || []) : (saved.data?.items || [])
  const canView = isPending || !!saved.data?.can_view_images
  const free = Math.max(0, DOCS_PER_RESIDENT - items.length)

  const add = async (doc) => {
    setCapturing(false)
    if (isPending) {
      onPendingChange?.([...(pending || []), {
        ...doc, id: `new-${Date.now()}`, size_bytes: doc.size, data_url: doc.dataUrl }])
      return
    }
    try {
      await residentApi.uploadDocument(residentId, {
        doc_type: doc.doc_type, label: doc.label, image: doc.image,
        source: doc.source, width: doc.width, height: doc.height })
      success('Document saved', `${sizeLabel(doc.size)}, stored with the resident.`)
      saved.reload()
    } catch (err) { error('Could not save the document', err.message) }
  }
  const remove = async (d) => {
    if (isPending) { onPendingChange?.((pending || []).filter((x) => x.id !== d.id)); return }
    setBusyId(d.id)
    try {
      await residentApi.deleteDocument(residentId, d.id)
      success('Document deleted')
      saved.reload()
    } catch (err) { error('Could not delete it', err.message) }
    finally { setBusyId(null) }
  }

  if (!isPending && saved.loading && !saved.data) return <Skeleton className="h-36" />

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {items.map((d) => (
          <div key={d.id} className="rounded-xl border border-line bg-white overflow-hidden">
            {canView && d.data_url ? (
              <button type="button" onClick={() => setViewing(d)} className="block w-full bg-slate-100">
                <img src={d.data_url} alt={docTypeLabel(d.doc_type)} className="w-full h-28 object-contain" />
              </button>
            ) : (
              <div className="h-28 bg-slate-50 flex flex-col items-center justify-center gap-1 text-slate-400">
                <Lock size={20} />
                <span className="text-2xs">Needs the KYC view permission</span>
              </div>
            )}
            <div className="p-2.5 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">{docTypeLabel(d.doc_type)}</p>
                <p className="text-2xs text-slate-500 truncate">
                  {[d.label, sizeLabel(d.size_bytes), d.source === 'upload' ? 'uploaded' : 'scanned'].filter(Boolean).join(' · ')}
                </p>
              </div>
              {canEdit && (
                <button type="button" onClick={() => remove(d)} disabled={busyId === d.id}
                  aria-label={`Delete ${docTypeLabel(d.doc_type)}`}
                  className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 disabled:opacity-50">
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          </div>
        ))}
        {canEdit && Array.from({ length: free }).map((_, i) => (
          <button key={`slot-${i}`} type="button" onClick={() => setCapturing(true)}
            className="h-[10.5rem] rounded-xl border-2 border-dashed border-line hover:border-brand-300 hover:bg-brand-50/40 flex flex-col items-center justify-center gap-1.5 text-slate-500 hover:text-brand-700 transition-colors">
            <Plus size={20} />
            <span className="text-sm font-medium">Add document</span>
            <span className="text-2xs">Scan or upload</span>
          </button>
        ))}
      </div>
      <p className="text-2xs text-slate-500 mt-2">
        Up to {DOCS_PER_RESIDENT} documents, each stored under {DOC_MAX_BYTES / 1024} KB.
        {isPending && ' They are saved when the resident is added.'}
      </p>

      <DocumentCapture open={capturing} onClose={() => setCapturing(false)} onDone={add} />

      <Modal open={!!viewing} onClose={() => setViewing(null)} size="md"
        title={viewing ? docTypeLabel(viewing.doc_type) : ''}
        subtitle={viewing ? [viewing.label, sizeLabel(viewing.size_bytes)].filter(Boolean).join(' · ') : ''}>
        {viewing?.data_url && (
          <div className="flex justify-center bg-slate-50 rounded-lg p-2">
            <img src={viewing.data_url} alt="Document" className="w-full h-auto max-w-lg" />
          </div>
        )}
      </Modal>
    </div>
  )
}
