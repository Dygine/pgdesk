/**
 * Reading a QR code with the camera.
 *
 * Two implementations behind one call, because the right answer differs by
 * platform and neither covers the other:
 *
 *   Android  Google's ML Kit scanner, through @capacitor-mlkit/barcode-scanning.
 *            It opens its own native screen, focuses and decodes far better
 *            than anything running in a WebView, and works in the poor light of
 *            a gate at eleven at night - which is the actual operating
 *            condition, not an edge case.
 *
 *   Browser  getUserMedia plus jsQR, decoding frames off a canvas. Slower and
 *            fussier about light, but it is the only option on a desktop at the
 *            front desk and on iOS Safari.
 *
 * The ML Kit path needs a module that ships with Google Play services rather
 * than inside the APK, so a phone can be missing it on first run. That download
 * is handled here instead of being left to fail as an unexplained scanner that
 * never opens.
 */
import { Capacitor } from '@capacitor/core'

export const isNativeScanner = () => Capacitor.isNativePlatform()

/** A refusal the screen has to explain, rather than an unexpected crash. */
export class ScannerError extends Error {
  constructor(code, message) {
    super(message)
    this.code = code
  }
}

async function mlkit() {
  const mod = await import('@capacitor-mlkit/barcode-scanning')
  return mod
}

/**
 * Camera permission, as an answer rather than an exception.
 *
 * Worth knowing: on Android a second denial is permanent until the user changes
 * it in system settings, and the OS stops showing the prompt entirely. A button
 * that silently does nothing forever is the result, so callers surface
 * `'denied'` as instructions rather than retrying.
 */
export async function requestCameraPermission() {
  if (!isNativeScanner()) {
    // The browser prompts on getUserMedia, so there is nothing to ask for yet.
    return 'prompt'
  }
  try {
    const { BarcodeScanner } = await mlkit()
    const status = await BarcodeScanner.requestPermissions()
    return status.camera ?? 'denied'
  } catch {
    return 'denied'
  }
}

/**
 * Open the native scanner and resolve with the decoded string.
 *
 * Resolves `null` when the user backs out, which is an ordinary thing to do and
 * not worth an error path of its own.
 */
export async function scanNative() {
  const { BarcodeScanner, BarcodeFormat } = await mlkit()

  const { supported } = await BarcodeScanner.isSupported()
  if (!supported) {
    throw new ScannerError(
      'unsupported', 'This device cannot scan QR codes with the camera.')
  }

  const permission = await requestCameraPermission()
  if (permission !== 'granted' && permission !== 'limited') {
    throw new ScannerError(
      'denied',
      'Camera permission is off. Allow the camera for PGDesk in your phone '
      + 'settings, then try again.')
  }

  // Ships with Play services, not with us. Absent on a fresh device, and on
  // one where the user has cleared Play services storage.
  const { available } = await BarcodeScanner.isGoogleBarcodeScannerModuleAvailable()
  if (!available) {
    try {
      await BarcodeScanner.installGoogleBarcodeScannerModule()
    } catch {
      throw new ScannerError(
        'module',
        'The scanner needs a one-time download from Google Play. Connect to '
        + 'the internet and try again.')
    }
  }

  const { barcodes } = await BarcodeScanner.scan({ formats: [BarcodeFormat.QrCode] })
  if (!barcodes?.length) return null
  return barcodes[0].rawValue ?? null
}

/**
 * Start the browser camera and hand back a stop function.
 *
 * `facingMode: environment` is a request, not a guarantee - a laptop has only
 * a front camera and will ignore it, which is correct behaviour rather than
 * something to fail on.
 */
export async function startWebCamera(videoEl) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new ScannerError(
      'unsupported',
      window.isSecureContext
        ? 'This browser cannot use the camera.'
        // Far and away the most common cause, and completely invisible
        // otherwise: getUserMedia simply does not exist over plain http.
        : 'The camera only works over https. Open the secure address, or use '
          + 'the app.')
  }

  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } }, audio: false,
    })
  } catch (err) {
    const name = err?.name || ''
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      throw new ScannerError(
        'denied', 'Camera permission was refused. Allow it in your browser, '
        + 'then try again.')
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') {
      throw new ScannerError('none', 'No camera was found on this device.')
    }
    throw new ScannerError('failed', 'Could not start the camera.')
  }

  videoEl.srcObject = stream
  videoEl.setAttribute('playsinline', 'true')   // iOS refuses to inline without it
  await videoEl.play().catch(() => {})

  return () => {
    try { stream.getTracks().forEach((t) => t.stop()) } catch { /* already gone */ }
    if (videoEl) videoEl.srcObject = null
  }
}

/**
 * Decode one frame. Returns the string or null.
 *
 * `dontInvert` because a PGDesk code is always dark on light: allowing jsQR to
 * try inverted costs a second pass over every frame for a case that cannot
 * occur, and the frame budget is what decides whether scanning feels instant.
 */
export function decodeFrame(jsQR, video, canvas) {
  const width = video.videoWidth
  const height = video.videoHeight
  if (!width || !height) return null

  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(video, 0, 0, width, height)

  const image = ctx.getImageData(0, 0, width, height)
  const found = jsQR(image.data, width, height, { inversionAttempts: 'dontInvert' })
  return found?.data ?? null
}
