import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Load something from the API and keep the four states every page needs:
 * data, loading, error and a reload function.
 *
 * Written rather than reached for because it is twenty lines and adding a data
 * library would be a bigger decision than this phase warrants.
 */
export function useApi(fetcher, deps = [], { enabled = true, initial = null } = {}) {
  const [data, setData] = useState(initial)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)

  // A slow first request must not overwrite the result of a faster later one.
  const latest = useRef(0)

  useEffect(() => {
    if (!enabled) { setLoading(false); return }
    const request = ++latest.current
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.resolve()
      .then(fetcher)
      .then((result) => {
        if (cancelled || request !== latest.current) return
        setData(result)
      })
      .catch((err) => {
        if (cancelled || request !== latest.current) return
        setError(err)
      })
      .finally(() => {
        if (!cancelled && request === latest.current) setLoading(false)
      })

    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, loading, error, reload, setData }
}

/** Wraps a mutation so a page gets `busy` and consistent error surfacing. */
export function useMutation(fn, { onSuccess, onError } = {}) {
  const [busy, setBusy] = useState(false)

  const run = useCallback(async (...args) => {
    setBusy(true)
    try {
      const result = await fn(...args)
      onSuccess?.(result)
      return { ok: true, data: result }
    } catch (err) {
      onError?.(err)
      return { ok: false, error: err }
    } finally {
      setBusy(false)
    }
  }, [fn, onSuccess, onError])

  return { run, busy }
}
