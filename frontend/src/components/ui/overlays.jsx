import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, AlertTriangle } from 'lucide-react'
import { Button } from './primitives'

const cx = (...a) => a.filter(Boolean).join(' ')

function useDismiss(open, onClose) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose])
}

/**
 * Modal on desktop, bottom sheet on phones — one component, one set of children.
 * Long forms stay usable on a 375px screen because the body scrolls, not the page.
 */
export function Modal({ open, onClose, title, subtitle, children, footer, size = 'md', className }) {
  const ref = useRef(null)
  useDismiss(open, onClose)
  useEffect(() => { if (open) setTimeout(() => ref.current?.focus(), 30) }, [open])
  if (!open) return null

  const width = { sm: 'sm:max-w-md', md: 'sm:max-w-2xl', lg: 'sm:max-w-4xl', xl: 'sm:max-w-6xl' }[size]

  return createPortal(
    <div className="fixed inset-0 z-[80] flex sm:items-center sm:justify-center items-end">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] animate-fadeIn" onClick={onClose} />
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={cx('relative w-full bg-white shadow-pop flex flex-col animate-slideUp sm:animate-popIn',
          'rounded-t-2xl sm:rounded-xl max-h-[92vh] sm:max-h-[88vh]', width, className)}>
        <div className="sm:hidden pt-2.5 pb-1 flex justify-center shrink-0">
          <span className="h-1 w-10 rounded-full bg-slate-300" />
        </div>
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-line shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label="Close"
            className="text-slate-400 hover:text-slate-700 p-1 -mr-1 -mt-0.5 shrink-0"><X size={20} /></button>
        </div>
        <div className="overflow-y-auto px-5 py-5 flex-1">{children}</div>
        {footer && (
          <div className="px-5 py-3.5 border-t border-line bg-slate-50/70 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0 safe-b sm:rounded-b-xl">
            {footer}
          </div>
        )}
      </div>
    </div>, document.body)
}

/** Side drawer — right on desktop, full width on phones. Used for record detail. */
export function Drawer({ open, onClose, title, subtitle, children, footer, width = 'max-w-xl' }) {
  useDismiss(open, onClose)
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[80] flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] animate-fadeIn" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label={title}
        className={cx('relative bg-white w-full h-full shadow-pop flex flex-col animate-slideRight', width)}>
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-line shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900 truncate">{title}</h2>
            {subtitle && <p className="text-sm text-slate-500 mt-0.5 truncate">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700 p-1 -mr-1 shrink-0">
            <X size={20} />
          </button>
        </div>
        <div className="overflow-y-auto flex-1">{children}</div>
        {footer && <div className="px-5 py-3.5 border-t border-line bg-slate-50/70 flex gap-2 shrink-0 safe-b">{footer}</div>}
      </div>
    </div>, document.body)
}

export function ConfirmDialog({ open, onClose, onConfirm, title, message, confirmLabel = 'Confirm', tone = 'danger' }) {
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm"
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant={tone} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</Button>
      </>}>
      <div className="flex gap-3.5">
        <span className={cx('h-10 w-10 rounded-full inline-flex items-center justify-center shrink-0',
          tone === 'danger' ? 'bg-rose-50 text-rose-600' : 'bg-amber-50 text-amber-600')}>
          <AlertTriangle size={20} />
        </span>
        <p className="text-sm text-slate-600 leading-relaxed pt-2">{message}</p>
      </div>
    </Modal>
  )
}
