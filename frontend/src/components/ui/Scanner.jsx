/**
 * The camera scanner.
 *
 * One component for two very different mechanisms. On Android it hands off to
 * the native ML Kit screen and renders nothing itself - the OS owns the camera
 * UI, and reimplementing a viewfinder in a WebView on top of it would be both
 * worse and pointless. In a browser it draws its own viewfinder over a video
 * element and decodes frames.
 *
 * Callers see one prop shape either way, so no page has to know which platform
 * it is on.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Camera, X, Loader2 } from 'lucide-react'
import {
  ScannerError, decodeFrame, isNativeScanner, scanNative, startWebCamera,
} from '@/lib/scanner'
import { looksLikeOurs } from '@/lib/qr'
import { Button, Card } from './primitives'
import { InlineAlert } from './feedback'

/**
 * @param open     mount and start the camera
 * @param onClose  user backed out, or the scan finished
 * @param onDetect called with the raw decoded string
 * @param title    heading shown on the web viewfinder
 * @param hint     one line telling the user what to point at
 * @param filter   reject codes that are not ours and keep scanning (default on)
 */
export function ScannerModal({
  open, onClose, onDetect, title = 'Scan a QR code',
  hint = 'Hold the code inside the frame.', filter = true,
}) {
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(true)
  const [ignored, setIgnored] = useState(false)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const stopRef = useRef(null)
  const rafRef = useRef(0)
  const doneRef = useRef(false)

  const finish = useCallback((value) => {
    if (doneRef.current) return
    doneRef.current = true
    onDetect?.(value)
  }, [onDetect])

  /* -------------------------------------------------------------- native */
  useEffect(() => {
    if (!open || !isNativeScanner()) return
    doneRef.current = false
    let cancelled = false

    scanNative()
      .then((value) => {
        if (cancelled) return
        // null means the user pressed back, which is not a failure.
        if (value === null) { onClose?.(); return }
        if (filter && !looksLikeOurs(value)) {
          setError(new ScannerError(
            'foreign', 'That is not a PGuru code. Scan the code on the card '
            + 'or at the gate.'))
          return
        }
        finish(value)
      })
      .catch((err) => { if (!cancelled) setError(err) })
      .finally(() => { if (!cancelled) setStarting(false) })

    return () => { cancelled = true }
  }, [open, filter, finish, onClose])

  /* ----------------------------------------------------------------- web */
  useEffect(() => {
    if (!open || isNativeScanner()) return
    doneRef.current = false
    setError(null)
    setStarting(true)
    setIgnored(false)

    let cancelled = false
    let jsQR = null

    const loop = () => {
      if (cancelled || doneRef.current) return
      const video = videoRef.current
      const canvas = canvasRef.current
      if (video && canvas && jsQR && video.readyState >= 2) {
        let value = null
        try {
          value = decodeFrame(jsQR, video, canvas)
        } catch { /* a frame that cannot be read is not worth stopping for */ }

        if (value) {
          if (!filter || looksLikeOurs(value)) {
            finish(value)
            return
          }
          // Something decoded, just not ours - a UPI sticker beside the gate is
          // the usual culprit. Say so rather than looking frozen.
          setIgnored(true)
        }
      }
      rafRef.current = requestAnimationFrame(loop)
    }

    ;(async () => {
      try {
        const mod = await import('jsqr')
        jsQR = mod.default ?? mod
        if (cancelled) return
        stopRef.current = await startWebCamera(videoRef.current)
        if (cancelled) { stopRef.current?.(); return }
        setStarting(false)
        rafRef.current = requestAnimationFrame(loop)
      } catch (err) {
        if (!cancelled) { setError(err); setStarting(false) }
      }
    })()

    return () => {
      cancelled = true
      cancelAnimationFrame(rafRef.current)
      // Releasing the track is what turns the camera light off. Skipping it
      // leaves the indicator on after the modal closes, which people
      // reasonably read as the app still watching them.
      stopRef.current?.()
      stopRef.current = null
    }
  }, [open, filter, finish])

  if (!open) return null

  // The OS is drawing its own full-screen scanner; anything here would sit
  // behind it and flash as it closes.
  if (isNativeScanner() && !error) return null

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/80 flex items-center justify-center p-4"
      role="dialog" aria-modal="true" aria-label={title} data-modal-open="true">
      <Card className="w-full max-w-md overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-5 py-3 border-b border-line">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <button type="button" onClick={onClose} aria-label="Close"
            data-modal-close
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg
                       text-slate-500 hover:bg-slate-100">
            <X size={16} />
          </button>
        </div>

        <div className="p-4">
          {error ? (
            <InlineAlert tone="error" title="Cannot scan">{error.message}</InlineAlert>
          ) : (
            <>
              <div className="relative rounded-xl overflow-hidden bg-slate-900 aspect-square">
                <video ref={videoRef} muted playsInline
                  className="absolute inset-0 h-full w-full object-cover" />
                <canvas ref={canvasRef} className="hidden" />

                {/* Corner marks rather than a full box: a solid overlay hides
                    exactly the part of the frame the user needs to aim. */}
                <div className="absolute inset-0 pointer-events-none">
                  <div className="absolute inset-[15%] rounded-lg">
                    {['top-0 left-0 border-t-2 border-l-2 rounded-tl-lg',
                      'top-0 right-0 border-t-2 border-r-2 rounded-tr-lg',
                      'bottom-0 left-0 border-b-2 border-l-2 rounded-bl-lg',
                      'bottom-0 right-0 border-b-2 border-r-2 rounded-br-lg',
                    ].map((pos) => (
                      <span key={pos}
                        className={`absolute h-8 w-8 border-white/90 ${pos}`} />
                    ))}
                  </div>
                </div>

                {starting && (
                  <div className="absolute inset-0 flex items-center justify-center
                                  text-white/80 gap-2 text-sm">
                    <Loader2 size={16} className="animate-spin" /> Starting camera…
                  </div>
                )}
              </div>

              <p className="text-xs text-slate-500 mt-3 text-center">{hint}</p>
              {ignored && (
                <p className="text-2xs text-amber-600 mt-1 text-center">
                  A code was read but it is not a PGuru one. Keep looking for
                  the PGuru code.
                </p>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-line flex justify-end">
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </Card>
    </div>
  )
}

/** The button that opens it, so pages do not each invent their own. */
export function ScanButton({ onClick, children = 'Scan with camera', ...rest }) {
  return <Button icon={Camera} onClick={onClick} {...rest}>{children}</Button>
}
