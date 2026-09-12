/**
 * Shrinking a listing photo to 5 KB.
 *
 * The same hard rule as an ID scan - 5,120 bytes, refused by the API and by a
 * CHECK constraint in the database - but a different job, so this is a separate
 * file rather than an option on docScan.js.
 *
 * What is different, and why
 * --------------------------
 * docScan.js converts to greyscale and stretches contrast, because at 5 KB the
 * only thing that matters on an Aadhaar card is whether the number is readable,
 * and colour costs bytes that buy nothing.
 *
 * A room is the opposite. A grey photo of a bedroom sells nothing; the warmth of
 * the light, whether the walls are clean, whether there is a window - all of
 * that is colour. So this keeps colour and spends the byte budget on it, which
 * means accepting fewer pixels. A 5 KB colour photo lands around 300-400 px on
 * the long side: perfectly good as a card thumbnail on a phone, visibly soft if
 * anyone opens it full screen on a laptop. That is the trade the 5 KB rule buys,
 * and it is the right one here because storage is PostgreSQL rather than a
 * bucket.
 *
 * Two ways in, matching the resident document flow the owner already knows:
 *   Take photo   - the phone camera opens (a plain file input with `capture`,
 *                  which the Android app already supports, so no new APK), and
 *                  the picture is shrunk here before it ever leaves the device.
 *   Upload image - taken as it is if it is already under 5 KB; anything bigger
 *                  is refused with its real size and can then be shrunk the
 *                  same way as a camera photo.
 *
 * Keep PHOTO_MAX_BYTES equal to PHOTO_MAX_BYTES in backend/app/models/branch.py.
 */
export const PHOTO_MAX_BYTES = 5 * 1024
export const PHOTOS_PER_BRANCH = 6
export const ACCEPTED_PHOTO_UPLOAD = ['image/jpeg', 'image/png', 'image/webp']

export const photoSizeLabel = (bytes) =>
  (bytes < 1024 ? `${bytes} bytes` : `${(bytes / 1024).toFixed(1)} KB`)

/**
 * Sizes tried for the longest side, largest first.
 *
 * Starts smaller than the document ladder. A colour photo carries roughly three
 * times the information per pixel, so beginning at 1100 px only wastes several
 * encode passes discovering that it cannot fit - every one of which is a frozen
 * half-second on a mid-range phone.
 */
const SIDES = [640, 560, 480, 420, 360, 320, 280, 240, 200, 160]

/**
 * Below this, WebP stops being a photograph and starts being coloured porridge.
 * Better to drop to fewer pixels at a decent quality than to keep the pixels and
 * lose every edge in the room.
 */
const READABLE_QUALITY = 0.32

/** 4:3 landscape. Room photos are shown in a fixed frame, so matching it here
 *  means the crop is decided by the owner rather than by CSS later. */
export const PHOTO_ASPECT = 4 / 3

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

/**
 * Draw the cropped region at `longest` px on its long side, in colour.
 *
 * A light blur is applied at the smallest sizes. That sounds backwards, but a
 * photo reduced to 200 px keeps high-frequency noise that the encoder then
 * spends its whole budget on; smoothing it first leaves more bytes for the
 * shapes a person actually looks at.
 */
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
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  if (longest <= 280) ctx.filter = 'blur(0.3px)'
  ctx.drawImage(source.img, sx, sy, sw, sh, 0, 0, cw, ch)
  ctx.filter = 'none'
  return canvas
}

/**
 * Crop and shrink until it is <= `limit` bytes, keeping colour.
 * `crop` is in fractions of the image (0..1).
 * Resolves { dataUrl, size, width, height, type }.
 */
export async function compressPhoto(file, { crop = { x: 0, y: 0, w: 1, h: 1 }, limit = PHOTO_MAX_BYTES } = {}) {
  const source = await loadImage(file)
  try {
    const type = await bestFormat()
    const longestCrop = Math.max(crop.w * source.width, crop.h * source.height)
    const first = Math.min(longestCrop, SIDES[0])
    const sides = [first, ...SIDES.filter((s) => s < first)]
    let fallback = null

    for (const side of sides) {
      const canvas = render(source, crop, side)
      // Binary search for the highest quality that still fits. Seven passes
      // lands within about half a percent, which is closer than the encoder is
      // consistent anyway.
      let lo = 0.05
      let hi = 0.95
      let best = null
      for (let k = 0; k < 7; k += 1) {
        const q = (lo + hi) / 2
        const blob = await toBlob(canvas, type, q)
        if (blob && blob.size <= limit) { best = { blob, q }; lo = q } else { hi = q }
      }
      if (best && best.q >= READABLE_QUALITY) return finish(best.blob, canvas, limit)
      if (best && !fallback) fallback = { blob: best.blob, canvas }
    }
    if (fallback) return finish(fallback.blob, fallback.canvas, limit)
    throw new Error('This photo could not be made small enough. Crop tighter and try again.')
  } finally {
    source.done()
  }
}

async function finish(blob, canvas, limit) {
  if (blob.size > limit) {
    throw new Error('The photo came out over 5 KB. Crop tighter and try again.')
  }
  return {
    dataUrl: await blobToDataUrl(blob), size: blob.size,
    width: canvas.width, height: canvas.height, type: blob.type,
  }
}

/**
 * An uploaded image is taken as it is - but only if it is already under 5 KB.
 * Anything larger is refused with its size, and the caller can offer to shrink
 * it. `err.tooLarge` is how the caller tells that case from a broken file.
 */
export async function acceptSmallPhoto(file) {
  if (!ACCEPTED_PHOTO_UPLOAD.includes(file.type)) {
    throw new Error('Only JPEG, PNG or WebP images can be uploaded.')
  }
  if (file.size > PHOTO_MAX_BYTES) {
    const err = new Error(`Photos must be under 5 KB. This one is ${photoSizeLabel(file.size)}.`)
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
