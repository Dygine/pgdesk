import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, CornerDownLeft, Loader2 } from 'lucide-react'
import { searchApi } from '@/services/api/searchApi'
import { Avatar, StatusBadge } from '@/components/ui'

const TYPE_LABEL = {
  resident: 'Resident', room: 'Room', bed: 'Bed', branch: 'Branch',
  invoice: 'Invoice', payment: 'Payment', complaint: 'Complaint',
  query: 'Query', visitor: 'Visitor', staff: 'Staff',
}

/** Long enough that typing does not fire a request per keystroke. */
const DEBOUNCE_MS = 220
const MIN_CHARS = 2

/**
 * Search is answered by the API, not by filtering a local store.
 *
 * There is deliberately no permission check in this component. The endpoint
 * gates every entity by its own module permission and filters to the caller's
 * branches, so whatever comes back is already exactly what this user may see.
 * Re-checking here would duplicate logic that could drift from the server's and
 * would imply the client is what enforces it.
 */
export function GlobalSearch({ compact }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const boxRef = useRef(null)

  // Guards against an early slow response landing after a later fast one.
  const latest = useRef(0)

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault(); setOpen(true); boxRef.current?.focus()
      }
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const term = q.trim()
    if (term.length < MIN_CHARS) {
      setResults([]); setLoading(false); setFailed(false)
      return
    }

    const request = ++latest.current
    setLoading(true)
    setFailed(false)

    const timer = setTimeout(() => {
      searchApi.search(term, { limit: 4 })
        .then((data) => {
          if (request !== latest.current) return
          setResults(data?.results || [])
          setActive(0)
        })
        .catch(() => {
          if (request !== latest.current) return
          setResults([]); setFailed(true)
        })
        .finally(() => {
          if (request === latest.current) setLoading(false)
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(timer)
  }, [q])

  const go = (r) => {
    if (r.link) navigate(r.link)
    setOpen(false)
    setQ('')
  }

  const showPanel = open && q.trim().length >= MIN_CHARS

  return (
    <div className="relative flex-1 max-w-lg">
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      <input ref={boxRef} value={q} type="search"
        onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 160)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
          if (e.key === 'Enter' && results[active]) go(results[active])
        }}
        placeholder={compact ? 'Search…' : 'Search residents, rooms, invoices…'}
        aria-label="Global search"
        className="w-full h-9 rounded-lg border border-line bg-slate-50 pl-9 pr-14 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white transition-colors" />

      {loading
        ? <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 animate-spin" />
        : <kbd className="hidden lg:block absolute right-2.5 top-1/2 -translate-y-1/2 text-2xs text-slate-400 border border-line rounded px-1.5 py-0.5 bg-white pointer-events-none">⌘K</kbd>}

      {showPanel && (
        <div className="absolute top-full left-0 right-0 mt-1.5 card shadow-pop max-h-[70vh] overflow-y-auto z-50 animate-popIn">
          {loading && results.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500 text-center">Searching…</p>
          ) : failed ? (
            <p className="px-4 py-6 text-sm text-slate-500 text-center">
              Search is unavailable right now. Try again in a moment.
            </p>
          ) : results.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500 text-center">
              Nothing matches “{q}”.
            </p>
          ) : results.map((r, i) => (
            <button key={`${r.type}_${r.id}`} onMouseDown={() => go(r)} onMouseEnter={() => setActive(i)}
              className={`w-full flex items-center gap-3 px-3.5 py-2.5 text-left border-b border-line last:border-0 ${i === active ? 'bg-slate-50' : ''}`}>
              {r.type === 'resident' || r.type === 'staff'
                ? <Avatar name={r.title} size="xs" />
                : <span className="h-6 w-6 rounded-md bg-slate-100 text-slate-500 inline-flex items-center justify-center text-2xs font-semibold shrink-0">
                    {(TYPE_LABEL[r.type] || '?')[0]}
                  </span>}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900 truncate">{r.title}</p>
                <p className="text-xs text-slate-500 truncate">
                  {TYPE_LABEL[r.type] || r.type}{r.subtitle ? ` · ${r.subtitle}` : ''}
                </p>
              </div>
              {r.badge && <StatusBadge status={r.badge} />}
              {i === active && <CornerDownLeft size={14} className="text-slate-300 shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
