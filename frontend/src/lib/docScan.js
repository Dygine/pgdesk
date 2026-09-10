/**
 * Scanning ID documents down to 5 KB.
 *
 * The rule is strict: 5 KB = 5,120 bytes per document, three per resident. The
 * server refuses anything larger and so does the database; this file is what
 * makes a phone photo (typically 2-4 MB) actually fit.
 *
 * How a photo becomes 5 KB without becoming mush:
 *   1. Crop to the document. Every pixel of table-top is a pixel of text lost.
 *   2. Grey, with the contrast stretched so the darkest 1% is black and the
 *      lightest 1% is white. Colour costs bytes and adds nothing to reading an
 *      ID number; full black-to-white range is what survives compression.
 *   3. Try the largest size first and search for the highest quality that fits.
 *      Accept it only if the quality is still readable (>= 0.3); otherwise step
 *      down in size and try again. More pixels at a sane quality reads better
 *      than a sharp thumbnail.
 *   4. WebP where the browser can write it (Chrome - so the Android app too),
 *      because it keeps edges of text cleaner than JPEG at this size.
 *
 * Keep DOC_MAX_BYTES equal to DOCUMENT_MAX_BYTES in backend/app/models/customer.py.
 */
export const DOC_MAX_BYTES = 5 * 1024
export const DOCS_PER_RESIDENT = 3
export const DOC_TYPES = [
  ['AADHAAR', 'Aadhaar'], ['PAN', 'PAN card'], ['PASSPORT', 'Passport'],
  ['DRIVING_LICENCE', 'Driving licence'], ['VOTER_ID', 'Voter ID'],
  ['OTHER', 'Other government ID'],
]
export const docTypeLabel = (t) => DOC_TYPES.find(([k]) => k === t)?.[1] || t
export const ACCEPTED_UPLOAD = ['image/jpeg', 'image/png', 'image/webp']
export const sizeLabel = (bytes) =>
  (bytes < 1024 ? `${bytes} bytes` : `${(bytes / 1024).toFixed(1)} KB`)

/** Sizes tried for the longest side, largest first. */
const SIDES = [1100, 960, 840, 720, 640, 560, 500, 440, 380, 320, 260, 200]
const READABLE_QUALITY = 0.3

export const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
  const r = new FileReader()
  r.onload = () => resolve(r.result)
  r.onerror = () => reject(new Error('Could not read the image.'))
  r.readAsDataURL(blob)
})

const toBlob = (canvas, type, quality) =>
  new Promise((resolve) => canvas.toBlob(resolve, type, quality))

let formatPromise = null
function bestFormat() {
  // Safari may quietly hand back a PNG when asked for WebP; then JPEG it is.
  formatPromise ||= (async () => {
    const c = document.createElement('canvas')
    c.width = 2; c.height = 2
    const b = await toBlob(c, 'image/webp', 0.5)
    return b?.type === 'image/webp' ? 'image/webp' : 'image/jpeg'
  })()
  return formatPromise
}

/** Decoded, the right way up (phones store rotation as EXIF, not pixels). */
async function loadImage(file) {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    return { img: bitmap, width: bitmap.width, height: bitmap.height, done: () => bitmap.close?.() }
  } catch {
    const url = URL.createObjectURL(file)
    const img = await new Promise((resolve, reject) => {
      const i = new Image()
      i.onload = () => resolve(i)
      i.onerror = () => reject(new Error('That file is not an image this device can read.'))
      i.src = url
    }).catch((e) => { URL.revokeObjectURL(url); throw e })
    return { img, width: img.naturalWidth, height: img.naturalHeight, done: () => URL.revokeObjectURL(url) }
  }
}

function render(source, crop, longest) {
  const sx = Math.round(crop.x * source.width)
  const sy = Math.round(crop.y * source.height)
  const sw = Math.max(1, Math.round(crop.w * source.width))
  const sh = Math.max(1, Math.round(crop.h * source.height))
  const scale = Math.min(1, longest / Math.max(sw, sh))
  const cw = Math.max(1, Math.round(sw * scale))
  const ch = Math.max(1, Math.round(sh * scale))

  const canvas = document.createElement('canvas')
  canvas.width = cw
  canvas.height = ch
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(source.img, sx, sy, sw, sh, 0, 0, cw, ch)

  const frame = ctx.getImageData(0, 0, cw, ch)
  const d = frame.data
  const lum = new Uint8ClampedArray(cw * ch)
  const hist = new Uint32Array(256)
  for (let i = 0, p = 0; i < d.length; i += 4, p += 1) {
    lum[p] = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000
    hist[lum[p]] += 1
  }
  const cut = lum.length * 0.01
  let lo = 0
  let hi = 255
  for (let v = 0, acc = 0; v < 256; v += 1) { acc += hist[v]; if (acc > cut) { lo = v; break } }
  for (let v = 255, acc = 0; v >= 0; v -= 1) { acc += hist[v]; if (acc > cut) { hi = v; break } }
  const span = Math.max(1, hi - lo)
  for (let i = 0, p = 0; i < d.length; i += 4, p += 1) {
    const v = ((lum[p] - lo) * 255) / span
    d[i] = v; d[i + 1] = v; d[i + 2] = v
  }
  ctx.putImageData(frame, 0, 0)
  return canvas
}

/**
 * Crop, grey, shrink until it is <= `limit` bytes. `crop` is in fractions of
 * the image (0..1). Resolves { dataUrl, size, width, height, type }.
 */
export async function compressDocument(file, { crop = { x: 0, y: 0, w: 1, h: 1 }, limit = DOC_MAX_BYTES } = {}) {
  const source = await loadImage(file)
  try {
    const type = await bestFormat()
    const longestCrop = Math.max(crop.w * source.width, crop.h * source.height)
    const first = Math.min(longestCrop, SIDES[0])
    const sides = [first, ...SIDES.filter((s) => s < first)]
    let fallback = null

    for (const side of sides) {
      const canvas = render(source, crop, side)
      let lo = 0.05
      let hi = 0.95
      let best = null
      for (let k = 0; k < 7; k += 1) {
        const q = (lo + hi) / 2
        const blob = await toBlob(canvas, type, q)
        if (blob && blob.size <= limit) { best = { blob, q }; lo = q } else { hi = q }
      }
      if (best && best.q >= READABLE_QUALITY) return finish(best.blob, canvas)
      if (best && !fallback) fallback = { blob: best.blob, canvas }
    }
    if (fallback) return finish(fallback.blob, fallback.canvas)
    throw new Error('This photo could not be made small enough. Crop closer to the document and try again.')
  } finally {
    source.done()
  }
}

async function finish(blob, canvas) {
  if (blob.size > DOC_MAX_BYTES) throw new Error('The scan came out over 5 KB. Crop closer and try again.')
  return { dataUrl: await blobToDataUrl(blob), size: blob.size, width: canvas.width, height: canvas.height, type: blob.type }
}

/**
 * An uploaded image is taken as it is - but only if it is already under 5 KB.
 * Anything larger is refused with its size, and the caller can offer to shrink.
 */
export async function acceptSmallUpload(file) {
  if (!ACCEPTED_UPLOAD.includes(file.type)) {
    throw new Error('Only JPEG, PNG or WebP images can be uploaded.')
  }
  if (file.size > DOC_MAX_BYTES) {
    const err = new Error(`Images must be under 5 KB. This one is ${sizeLabel(file.size)}.`)
    err.tooLarge = true
    throw err
  }
  const dataUrl = await blobToDataUrl(file)
  const dims = await new Promise((resolve) => {
    const i = new Image()
    i.onload = () => resolve({ width: i.naturalWidth, height: i.naturalHeight })
    i.onerror = () => resolve({})
    i.src = dataUrl
  })
  return { dataUrl, size: file.size, ...dims, type: file.type }
}
