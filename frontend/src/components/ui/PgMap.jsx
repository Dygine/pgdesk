/**
 * The map on Find PG - drop a pin anywhere and search around it.
 *
 * Why this exists
 * ---------------
 * "Near me" answers the question of someone standing where they want to live.
 * It answers nothing for the much more common case: finding a PG for a friend,
 * or near a campus, or beside the office you start at next month. For that you
 * have to be able to point at a place you are not standing in - which needs a
 * map you can see, not a list of place names.
 *
 * So there are three ways to choose a point, and all three end in the same
 * place: a latitude, a longitude and a label that the search runs against.
 *   - Use my location   (GPS, the old default, still one tap)
 *   - Type an area      (geocoded by the API, which proxies OpenStreetMap)
 *   - Tap or drag       (the pin goes where you put it, anywhere on earth)
 *
 * Why Leaflet and OpenStreetMap
 * -----------------------------
 * Free, with no API key and no billing account attached to a card that can be
 * forgotten about. Google Maps would need a key, a quota and a monthly bill
 * that starts small and does not stay small once a seeker-facing search page is
 * getting traffic. OSM's tile usage policy asks for a real referrer and
 * sensible volumes, both of which a normal product does naturally.
 *
 * Leaflet is loaded lazily, on first open. It is around 40 KB gzipped, and
 * nobody who never opens the map should pay for it on a phone.
 *
 * Note on the marker icon: Leaflet's default icon is loaded from image files
 * resolved relative to the CSS, which a bundler rewrites and then cannot find -
 * the classic "markers are invisible" bug. A divIcon with inline SVG has no
 * asset to lose, so that is what this uses.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Crosshair, Loader2, MapPin, Search, Check } from 'lucide-react'
import { publicApi } from '@/services/api/publicApi'
import { Button, Input, InlineAlert } from '@/components/ui'

/** Bengaluru, as a last resort when there is no position and no search yet. */
const FALLBACK_CENTRE = { latitude: 12.9716, longitude: 77.5946 }

let leafletPromise = null
/** Load Leaflet and its stylesheet once, on first use. */
function loadLeaflet() {
  leafletPromise ||= (async () => {
    const [L] = await Promise.all([
      import('leaflet'),
      import('leaflet/dist/leaflet.css'),
    ])
    return L.default || L
  })()
  return leafletPromise
}

const pinIcon = (L, { colour = '#1d4ed8' } = {}) => L.divIcon({
  className: '',
  html: `<svg width="30" height="40" viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg">
    <path d="M15 39c0 0-13-15.5-13-24A13 13 0 0 1 28 15c0 8.5-13 24-13 24z"
      fill="${colour}" stroke="#ffffff" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="15" cy="15" r="5" fill="#ffffff"/>
  </svg>`,
  iconSize: [30, 40],
  iconAnchor: [15, 39],
  popupAnchor: [0, -36],
})

const resultIcon = (L) => L.divIcon({
  className: '',
  html: `<span style="display:block;width:16px;height:16px;border-radius:9999px;
    background:#059669;border:3px solid #ffffff;box-shadow:0 1px 4px rgba(15,23,42,.4)"></span>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

/**
 * An interactive map with one draggable pin, and optional read-only markers for
 * search results.
 *
 * `value`      { latitude, longitude } - where the pin sits now
 * `onPick`     called with { latitude, longitude } when the pin is moved
 * `results`    [{ id, latitude, longitude, name }] - shown as small dots
 * `onOpenResult` called with a result id when its dot is tapped
 */
export function PgMap({ value, onPick, results = [], onOpenResult, radiusKm, height = 300 }) {
  const holder = useRef(null)
  const map = useRef(null)
  const pin = useRef(null)
  const ring = useRef(null)
  const layer = useRef(null)
  const lib = useRef(null)
  const pick = useRef(onPick)
  const open = useRef(onOpenResult)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  // Kept in refs so moving the pin never needs the map rebuilt.
  useEffect(() => { pick.current = onPick }, [onPick])
  useEffect(() => { open.current = onOpenResult }, [onOpenResult])

  /* ------------------------------------------------------------ build once */
  useEffect(() => {
    let dead = false
    ;(async () => {
      let L
      try {
        L = await loadLeaflet()
      } catch {
        if (!dead) setFailed(true)          // offline on first open; list still works
        return
      }
      if (dead || !holder.current || map.current) return
      lib.current = L

      const start = value || FALLBACK_CENTRE
      const instance = L.map(holder.current, {
        center: [start.latitude, start.longitude],
        zoom: value ? 14 : 11,
        zoomControl: true,
        attributionControl: true,
      })
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        // Required by the OSM tile usage policy, and simply correct.
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(instance)

      pin.current = L.marker([start.latitude, start.longitude], {
        draggable: true, icon: pinIcon(L), keyboard: true,
        title: 'Drag to move the search area',
      }).addTo(instance)

      pin.current.on('dragend', () => {
        const { lat, lng } = pin.current.getLatLng()
        pick.current?.({ latitude: lat, longitude: lng })
      })
      instance.on('click', (e) => {
        pin.current.setLatLng(e.latlng)
        pick.current?.({ latitude: e.latlng.lat, longitude: e.latlng.lng })
      })

      layer.current = L.layerGroup().addTo(instance)
      map.current = instance
      if (!dead) setReady(true)

      // A map built inside a sheet that was still animating measures itself at
      // the wrong size and renders a grey strip. One nudge after layout settles.
      setTimeout(() => instance.invalidateSize(), 180)
    })()
    return () => {
      dead = true
      map.current?.remove()
      map.current = null
      pin.current = null
      ring.current = null
      layer.current = null
    }
    // Built once on mount. Position changes are handled by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ----------------------------------------------- follow the chosen point */
  useEffect(() => {
    if (!ready || !value || !map.current || !pin.current) return
    const here = pin.current.getLatLng()
    const moved = Math.abs(here.lat - value.latitude) > 1e-7
      || Math.abs(here.lng - value.longitude) > 1e-7
    if (moved) pin.current.setLatLng([value.latitude, value.longitude])
    map.current.setView([value.latitude, value.longitude],
      Math.max(map.current.getZoom(), 13), { animate: true })
  }, [ready, value?.latitude, value?.longitude])

  /* ------------------------------------------------------- the search ring */
  useEffect(() => {
    const L = lib.current
    if (!ready || !L || !map.current || !value || !radiusKm) return undefined
    ring.current?.remove()
    ring.current = L.circle([value.latitude, value.longitude], {
      radius: radiusKm * 1000,
      color: '#1d4ed8', weight: 1, opacity: 0.5,
      fillColor: '#1d4ed8', fillOpacity: 0.06,
    }).addTo(map.current)
    return () => { ring.current?.remove(); ring.current = null }
  }, [ready, value?.latitude, value?.longitude, radiusKm])

  /* ------------------------------------------------------------- the dots */
  useEffect(() => {
    const L = lib.current
    if (!ready || !L || !layer.current) return
    layer.current.clearLayers()
    results.forEach((r) => {
      if (r.latitude == null || r.longitude == null) return
      const dot = L.marker([r.latitude, r.longitude], { icon: resultIcon(L), title: r.name })
      dot.bindTooltip(r.name, { direction: 'top', offset: [0, -10] })
      dot.on('click', () => open.current?.(r.id))
      dot.addTo(layer.current)
    })
  }, [ready, results])

  if (failed) {
    return (
      <InlineAlert tone="info" title="The map could not load">
        You are probably offline. Searching by area name still works, and so does
        “Use my location”.
      </InlineAlert>
    )
  }

  return (
    <div className="relative rounded-xl overflow-hidden border border-line bg-slate-100"
      style={{ height }}>
      <div ref={holder} className="absolute inset-0" aria-label="Map of the search area" />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-100">
          <Loader2 size={20} className="animate-spin text-slate-400" />
        </div>
      )}
    </div>
  )
}

/**
 * The full "where do you want to look?" sheet body: a map, a search box and a
 * GPS button, sharing one chosen point.
 *
 * Kept separate from the modal chrome so the same thing can be dropped into the
 * search screen inline later without a dialog around it.
 */
export function PlaceChooser({ value, onChange, onUseGps, locating, height = 280 }) {
  const [q, setQ] = useState('')
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null)
  const timer = useRef(0)

  /* Type an area; the API geocodes it. Debounced, because every keystroke
     otherwise becomes a request to a geocoder with a one-per-second policy. */
  useEffect(() => {
    clearTimeout(timer.current)
    const term = q.trim()
    if (term.length < 2) { setItems([]); setBusy(false); return undefined }
    setBusy(true)
    timer.current = setTimeout(async () => {
      try {
        const res = await publicApi.places(term)
        const found = res?.places || []
        setItems(found)
        setNote(res?.source === 'listings' && found.length
          ? 'Showing areas that have listed PGs.' : null)
      } catch {
        setItems([])
        setNote('Area search is unavailable right now. Tap the map to drop a pin instead.')
      } finally { setBusy(false) }
    }, 350)
    return () => clearTimeout(timer.current)
  }, [q])

  const dropped = useCallback((point) => {
    // A dragged pin has no name until the API gives it one. Say where it is in
    // the meantime rather than showing nothing.
    onChange({ ...point, label: 'the pin you dropped' })
    ;(async () => {
      try {
        const found = await publicApi.reversePlace(point.latitude, point.longitude)
        if (found?.label) onChange({ ...point, label: found.label })
      } catch { /* coordinates work fine without a name */ }
    })()
  }, [onChange])

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <div className="relative flex-1 min-w-0">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <Input value={q} placeholder="Type an area, locality or landmark" className="pl-9 pr-9"
            onChange={(e) => setQ(e.target.value)} />
          {busy && <Loader2 size={15} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-slate-400" />}
        </div>
        <Button icon={Crosshair} loading={locating} onClick={onUseGps} aria-label="Use my location">
          <span className="hidden sm:inline">Near me</span>
        </Button>
      </div>

      {items.length > 0 && (
        <ul className="divide-y divide-line rounded-lg border border-line max-h-44 overflow-y-auto">
          {items.map((p) => (
            <li key={`${p.latitude},${p.longitude},${p.label}`}>
              <button type="button"
                onClick={() => {
                  onChange({ latitude: p.latitude, longitude: p.longitude, label: p.label })
                  setItems([]); setQ('')
                }}
                className="w-full text-left py-2.5 px-3 flex items-start gap-2.5 hover:bg-slate-50">
                <MapPin size={15} className="text-slate-400 mt-0.5 shrink-0" />
                <span className="min-w-0">
                  <span className="block text-sm text-slate-900 truncate">{p.label}</span>
                  <span className="block text-xs text-slate-500 truncate">{p.detail}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {note && <p className="text-xs text-slate-500">{note}</p>}

      <PgMap value={value} onPick={dropped} height={height} />

      <p className="text-xs text-slate-500 flex items-start gap-1.5">
        <MapPin size={13} className="mt-0.5 shrink-0 text-slate-400" />
        Tap anywhere on the map, or drag the pin, to search around that spot —
        handy when you are looking for someone else.
      </p>

      {value && (
        <p className="text-sm text-slate-700 inline-flex items-center gap-1.5">
          <Check size={15} className="text-emerald-600 shrink-0" />
          Searching near <span className="font-medium">{value.label || 'the pin you dropped'}</span>
        </p>
      )}
    </div>
  )
}
