import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, ChevronLeft, ChevronRight, ChevronsUpDown } from 'lucide-react'
import { EmptyState } from './feedback'

const cx = (...a) => a.filter(Boolean).join(' ')

/**
 * ONE table component for the whole product.
 *  - >= lg  : real table
 *  - < lg   : the same rows rendered through `mobileCard`
 * There is no second mobile table anywhere in this codebase.
 *
 * columns: [{ key, header, render?, sortValue?, align?, width?, hideBelow? }]
 */
export function DataTable({
  columns, rows, rowKey = (r) => r.id, onRowClick, mobileCard,
  empty, pageSize = 12, dense = false, initialSort, className, footer,
}) {
  const [sort, setSort] = useState(initialSort || null)
  const [page, setPage] = useState(1)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return rows
    const val = col.sortValue || ((r) => r[sort.key])
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b)
      if (x == null) return 1
      if (y == null) return -1
      const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'en')
      return sort.dir === 'asc' ? r : -r
    })
  }, [rows, sort, columns])

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const current = Math.min(page, pages)
  const slice = sorted.slice((current - 1) * pageSize, current * pageSize)

  const toggleSort = (key) =>
    setSort((s) => (s?.key !== key ? { key, dir: 'asc' } : s.dir === 'asc' ? { key, dir: 'desc' } : null))

  if (!rows.length) return empty || <EmptyState title="Nothing here yet" />

  return (
    <div className={className}>
      {/* Desktop / large tablet */}
      <div className="hidden lg:block overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-line">
              {columns.map((c) => (
                <th key={c.key} scope="col" style={c.width ? { width: c.width } : undefined}
                  className={cx('px-4 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap',
                    c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left',
                    c.hideBelow === 'xl' && 'hidden xl:table-cell')}>
                  {c.sortable === false ? c.header : (
                    <button onClick={() => toggleSort(c.key)}
                      className={cx('inline-flex items-center gap-1 hover:text-slate-800 transition-colors',
                        c.align === 'right' && 'flex-row-reverse')}>
                      {c.header}
                      {sort?.key === c.key
                        ? (sort.dir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />)
                        : <ChevronsUpDown size={13} className="text-slate-300" />}
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={onRowClick ? (e) => { if (e.key === 'Enter') onRowClick(r) } : undefined}
                className={cx('border-b border-line/70 last:border-0 transition-colors',
                  onRowClick && 'cursor-pointer hover:bg-slate-50 focus:bg-slate-50')}>
                {columns.map((c) => (
                  <td key={c.key}
                    className={cx('px-4 align-middle', dense ? 'py-2' : 'py-3',
                      c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left',
                      c.hideBelow === 'xl' && 'hidden xl:table-cell')}>
                    {c.render ? c.render(r) : <span className="text-slate-700">{r[c.key]}</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {footer && <tfoot className="border-t border-line bg-slate-50/60">{footer}</tfoot>}
        </table>
      </div>

      {/* Phone / small tablet — same rows, card shape */}
      <div className="lg:hidden divide-y divide-line">
        {slice.map((r) => (
          <div key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined}
            role={onRowClick ? 'button' : undefined} tabIndex={onRowClick ? 0 : undefined}
            onKeyDown={onRowClick ? (e) => { if (e.key === 'Enter') onRowClick(r) } : undefined}
            className={cx('p-3.5', onRowClick && 'active:bg-slate-50 cursor-pointer')}>
            {mobileCard ? mobileCard(r) : <MobileDataCard row={r} columns={columns} />}
          </div>
        ))}
      </div>

      {pages > 1 && (
        <Pagination page={current} pages={pages} total={sorted.length}
          from={(current - 1) * pageSize + 1} to={Math.min(current * pageSize, sorted.length)}
          onChange={setPage} />
      )}
    </div>
  )
}

/** Generic fallback card — used when a page doesn't supply its own mobileCard. */
export function MobileDataCard({ row, columns }) {
  const [first, ...rest] = columns
  return (
    <div className="space-y-2">
      <div>{first.render ? first.render(row) : row[first.key]}</div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {rest.filter((c) => c.key !== 'actions').map((c) => (
          <div key={c.key} className="min-w-0">
            <dt className="text-2xs text-slate-500">{c.header}</dt>
            <dd className="text-sm text-slate-800 truncate">{c.render ? c.render(row) : row[c.key] ?? '—'}</dd>
          </div>
        ))}
      </dl>
      {columns.find((c) => c.key === 'actions') && (
        <div className="pt-1">{columns.find((c) => c.key === 'actions').render(row)}</div>
      )}
    </div>
  )
}

export function Pagination({ page, pages, total, from, to, onChange }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-line">
      <p className="text-xs text-slate-500 tnum">
        <span className="hidden sm:inline">Showing </span>{from}–{to} of {total}
      </p>
      <div className="flex items-center gap-1">
        <button onClick={() => onChange(page - 1)} disabled={page === 1} aria-label="Previous page"
          className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-line text-slate-600 disabled:opacity-40 hover:bg-slate-50">
          <ChevronLeft size={16} />
        </button>
        <span className="px-2 text-xs text-slate-600 tnum">{page} / {pages}</span>
        <button onClick={() => onChange(page + 1)} disabled={page === pages} aria-label="Next page"
          className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-line text-slate-600 disabled:opacity-40 hover:bg-slate-50">
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}
