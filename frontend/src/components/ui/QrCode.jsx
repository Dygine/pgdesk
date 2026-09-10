/**
 * A real, scannable QR code.
 *
 * This replaces a placeholder that drew a hash-derived grid of squares. It
 * looked convincing to a person and could not be decoded by any scanner, which
 * is the worst combination available: nothing about the screen suggested the
 * feature did not work, so the failure surfaced at a gate rather than in
 * testing.
 *
 * Error correction is set to M (about 15% recoverable). Gate cards get creased,
 * carried in wallets and photographed at an angle, and H would be the obvious
 * choice for that - but H also inflates the module count, and at the size these
 * are printed on a resident card the finer grid decodes worse in poor light
 * than a coarser one with less redundancy. M is the point where those two lines
 * cross for a payload this short.
 */
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'

export function QrCode({
  value,
  size = 220,
  className = '',
  alt = 'QR code',
  margin = 2,
}) {
  const [src, setSrc] = useState(null)
  const [failed, setFailed] = useState(false)
  const latest = useRef(0)

  useEffect(() => {
    if (!value) { setSrc(null); return }
    const request = ++latest.current
    let cancelled = false

    QRCode.toDataURL(String(value), {
      // Rendered at twice the display size so it stays sharp on a phone screen
      // and, more importantly, survives being printed: a card generated from a
      // 220px image looks fine on a monitor and scans badly on paper.
      width: size * 2,
      margin,
      errorCorrectionLevel: 'M',
      color: { dark: '#0F172A', light: '#FFFFFF' },
    })
      .then((url) => {
        if (cancelled || request !== latest.current) return
        setSrc(url)
        setFailed(false)
      })
      .catch(() => {
        if (cancelled || request !== latest.current) return
        setFailed(true)
      })

    return () => { cancelled = true }
  }, [value, size, margin])

  if (failed) {
    return (
      <div className={`flex items-center justify-center rounded-lg bg-slate-50 border border-line text-center p-4 ${className}`}
        style={{ width: size, height: size }}>
        <p className="text-xs text-slate-500">
          This code could not be drawn. Ask the office to reissue it.
        </p>
      </div>
    )
  }

  if (!src) {
    return (
      <div className={`rounded-lg bg-slate-100 animate-pulse ${className}`}
        style={{ width: size, height: size }} aria-hidden="true" />
    )
  }

  return (
    <img src={src} width={size} height={size} alt={alt}
      // Nearest-neighbour: smoothing a QR on upscale rounds the module edges
      // and is a real cause of failed reads on cheap scanners.
      style={{ imageRendering: 'pixelated' }}
      className={`rounded-lg bg-white ${className}`} />
  )
}
