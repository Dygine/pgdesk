import { Search, X, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Select } from './primitives'

const cx = (...a) => a.filter(Boolean).join(' ')

export function SearchBar({ value, onChange, placeholder = 'Search…', className, autoFocus }) {
  return (
    <div className={cx('relative', className)}>
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        autoFocus={autoFocus} type="search" aria-label={placeholder}
        className="w-full h-10 rounded-lg border border-line bg-white pl-9 pr-9 text-sm text-slate-900 placeholder:text-slate-400 hover:border-slate-300 transition-colors" />
      {value && (
        <button onClick={() => onChange('')} aria-label="Clear search"
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
          <X size={15} />
        </button>
      )}
    </div>
  )
}

/**
 * Filters collapse behind a button on phones and sit inline on desktop —
 * same filter definitions, no duplicated markup.
 */
export function FilterBar({ search, onSearch, searchPlaceholder, filters = [], actions, className }) {
  const [openMobile, setOpenMobile] = useState(false)
  const activeCount = filters.filter((f) => f.value && f.value !== 'all').length

  return (
    <div className={cx('space-y-3', className)}>
      <div className="flex gap-2">
        {onSearch && <SearchBar value={search} onChange={onSearch} placeholder={searchPlaceholder} className="flex-1 min-w-0" />}
        {filters.length > 0 && (
          <button onClick={() => setOpenMobile((v) => !v)}
            className={cx('sm:hidden h-10 px-3 rounded-lg border text-sm font-medium inline-flex items-center gap-1.5 shrink-0',
              activeCount ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-line bg-white text-slate-600')}>
            <SlidersHorizontal size={15} />
            {activeCount > 0 && <span className="tnum">{activeCount}</span>}
          </button>
        )}
        {actions && <div className="hidden sm:flex gap-2 shrink-0">{actions}</div>}
      </div>

      {filters.length > 0 && (
        <div className={cx('gap-2 flex-wrap', openMobile ? 'flex' : 'hidden sm:flex')}>
          {filters.map((f) => (
            <Select key={f.key} value={f.value} onChange={(e) => f.onChange(e.target.value)} aria-label={f.label}
              className="w-full sm:w-auto sm:min-w-[9.5rem]">
              <option value="all">{f.label}: All</option>
              {f.options.map((o) => (
                <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>
              ))}
            </Select>
          ))}
        </div>
      )}

      {actions && <div className="sm:hidden flex gap-2">{actions}</div>}
    </div>
  )
}
