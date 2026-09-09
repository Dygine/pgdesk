import { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react'

const ToastCtx = createContext(null)
export const useToast = () => useContext(ToastCtx)

const TONES = {
  success: { icon: CheckCircle2, cls: 'text-emerald-600', bar: 'bg-emerald-500' },
  error:   { icon: XCircle,      cls: 'text-rose-600',    bar: 'bg-rose-500' },
  warn:    { icon: AlertTriangle,cls: 'text-amber-600',   bar: 'bg-amber-500' },
  info:    { icon: Info,         cls: 'text-brand-600',   bar: 'bg-brand-500' },
}

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])

  const dismiss = useCallback((id) => setItems((x) => x.filter((t) => t.id !== id)), [])

  const push = useCallback((message, tone = 'success', detail) => {
    const id = Math.random().toString(36).slice(2)
    setItems((x) => [...x, { id, message, tone, detail }])
    setTimeout(() => dismiss(id), tone === 'error' ? 6500 : 4000)
  }, [dismiss])

  const api = {
    toast: push,
    success: (m, d) => push(m, 'success', d),
    error: (m, d) => push(m, 'error', d),
    warn: (m, d) => push(m, 'warn', d),
    info: (m, d) => push(m, 'info', d),
  }

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div
        className="fixed z-[90] bottom-20 sm:bottom-6 right-3 left-3 sm:left-auto sm:right-6 sm:w-[26rem] flex flex-col gap-2 pointer-events-none safe-b"
        role="status" aria-live="polite"
      >
        {items.map((t) => {
          const tone = TONES[t.tone] || TONES.info
          const Icon = tone.icon
          return (
            <div key={t.id}
              className="pointer-events-auto card shadow-pop overflow-hidden flex animate-popIn">
              <span className={`w-1 shrink-0 ${tone.bar}`} />
              <div className="flex items-start gap-3 p-3.5 flex-1 min-w-0">
                <Icon size={18} className={`${tone.cls} shrink-0 mt-0.5`} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-900">{t.message}</p>
                  {t.detail && <p className="text-xs text-slate-500 mt-0.5">{t.detail}</p>}
                </div>
                <button onClick={() => dismiss(t.id)} aria-label="Dismiss"
                  className="text-slate-400 hover:text-slate-700 shrink-0 p-0.5">
                  <X size={15} />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
