import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { makeCan } from '@/lib/rbac'
import { subscriptionState } from '@/lib/limits'
import { authApi } from '@/services/api/authApi'
import { SESSION, setSessionExpiredHandler, tokenStore } from '@/services/api/client'

const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

/**
 * Authentication and the identity every screen reads.
 *
 * Everything here comes from the API. The password is verified by FastAPI
 * against an Argon2 hash; the role, branch list, permission set, organisation
 * and subscription all come back from /auth/me. Nothing is decided in the
 * browser and nothing is looked up in a local store.
 *
 * `can()` is wired to the server's effective permission list, so navigation and
 * buttons reflect real authorisation — but it is a display decision only. Every
 * protected operation is checked again on the server, which is what actually
 * enforces it.
 */
export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null)     // what /auth/me returned
  const [status, setStatus] = useState('loading')  // loading | authenticated | anonymous | offline
  const [branchScope, setBranchScope] = useState('all')

  /**
   * Restore the session on load.
   *
   * The access token lived in memory and did not survive the reload, but the
   * refresh cookie did. Whether it is still valid is a question only the server
   * can answer — the cookie is HttpOnly, so there is nothing to inspect here.
   * So we always ask: `restore()` exchanges the cookie for a fresh access
   * token, and a failure simply means nobody is signed in.
   */
  const [attempts, setAttempts] = useState(0)

  /**
   * Restore the session: at launch, and again whenever the server could not be
   * reached. Only a definite "no" from the server lands on the login screen.
   * Unreachable means 'offline': the saved login is kept and we keep trying,
   * because the usual cause is a server waking up or a deploy in progress -
   * not the person having signed out.
   */
  const restoreSession = useCallback(async () => {
    const result = await authApi.restore()
    if (result === SESSION.REJECTED) { setAccount(null); setStatus('anonymous'); return }
    if (result !== SESSION.OK) { setStatus('offline'); setAttempts((n) => n + 1); return }
    try {
      const me = await authApi.me()
      setAccount(me); setStatus('authenticated'); setAttempts(0)
    } catch (err) {
      if (err?.status === 401) {
        tokenStore.clear(); setAccount(null); setStatus('anonymous')
      } else {
        setStatus('offline'); setAttempts((n) => n + 1)
      }
    }
  }, [])

  useEffect(() => { restoreSession() }, [restoreSession])

  // While offline: retry on a backoff (2s, 4s, 8s, then every 15s), and
  // immediately when the phone gets signal back or the app comes to the front.
  useEffect(() => {
    if (status !== 'offline') return undefined
    const delay = Math.min(15000, 2000 * 2 ** Math.max(0, attempts - 1))
    const timer = setTimeout(restoreSession, delay)
    const now = () => restoreSession()
    window.addEventListener('online', now)
    window.addEventListener('pgguru:resume', now)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('online', now)
      window.removeEventListener('pgguru:resume', now)
    }
  }, [status, attempts, restoreSession])

  /* One place decides what happens when a session dies mid-session. */
  useEffect(() => {
    setSessionExpiredHandler(() => { setAccount(null); setStatus('anonymous') })
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (email, password) => {
    try {
      const user = await authApi.login(email, password)
      setAccount(user)
      setStatus('authenticated')
      setBranchScope('all')
      return { ok: true, portal: user.portal, user }
    } catch (err) {
      return { ok: false, error: err.message || 'Could not sign you in.' }
    }
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setAccount(null)
    setStatus('anonymous')
    setBranchScope('all')
  }, [])

  /** The resident's first sign-in, by scanning the QR their PG showed them. */
  const loginWithQr = useCallback(async (code) => {
    try {
      const user = await authApi.qrLogin(code)
      setAccount(user)
      setStatus('authenticated')
      setBranchScope('all')
      return { ok: true, portal: user.portal, user }
    } catch (err) {
      return { ok: false, error: err.message || 'Could not sign you in.', code: err.code }
    }
  }, [])

  /** Swap in a fresh account, e.g. the one change-password returns. */
  const replaceAccount = useCallback((user) => { if (user) setAccount(user) }, [])

  const refreshAccount = useCallback(async () => {
    try {
      const me = await authApi.me()
      setAccount(me)
      return me
    } catch {
      return null
    }
  }, [])

  /**
   * Impersonation is a master-admin feature (`master.impersonate`) with no
   * endpoint yet. It deliberately does NOT fall back to switching the local
   * session: that would be a second, unauthenticated way into a tenant, which
   * is exactly what real authentication is supposed to remove.
   */
  const loginAs = useCallback(() => ({
    ok: false,
    error: 'Impersonation needs a backend endpoint and is not available in this build.',
  }), [])

  const value = useMemo(() => {
    const base = {
      user: null, customer: null, role: null, org: null, can: () => false,
      branches: [], branchScope: 'all', setBranchScope,
      apiBranches: [], apiBranchIds: [], activeBranchId: null,
      login, logout, loginAs, loginWithQr, replaceAccount, refreshAccount,
      isMaster: false, subscription: null,
      account: null, status, isAuthenticated: false, isLoading: status === 'loading',
      permissions: [], portal: null, mustChangePassword: false,
    }

    if (!account) return base

    const shared = {
      account,
      status,
      isAuthenticated: true,
      isLoading: false,
      permissions: account.permissions || [],
      portal: account.portal,
      mustChangePassword: Boolean(account.must_change_password),
    }

    /* ------------------------------------------------------------ master */
    if (account.portal === 'master') {
      return {
        ...base, ...shared,
        user: { id: account.id, name: account.name, email: account.email, isMaster: true,
                organizationId: null, status: account.status },
        role: { name: 'Master Admin' },
        can: makeCan(new Set(account.permissions || [])),
        isMaster: true,
      }
    }

    /* ---------------------------------------------------------- resident */
    if (account.portal === 'customer') {
      // The portal's own pages fetch their data from /me/*, which derives the
      // resident from the token. This exposes identity only.
      return {
        ...base, ...shared,
        customer: {
          id: account.id, name: account.name, email: account.email,
          phone: account.phone, status: account.status,
        },
        role: { name: 'Resident' },
        org: account.organization || null,
        can: () => false,             // residents hold no module permissions
        subscription: subscriptionState(account.organization),
      }
    }

    /* --------------------------------------------------------- org staff */
    const apiBranches = account.branches || []
    const inScope = (code) => branchScope === 'all' || branchScope === code
    const apiBranchIds = apiBranches.filter((b) => inScope(b.code)).map((b) => b.id)
    const activeBranchId =
      branchScope === 'all' ? null : apiBranches.find((b) => b.code === branchScope)?.id ?? null

    return {
      ...base, ...shared,
      user: {
        id: account.id,
        name: account.name,
        email: account.email,
        phone: account.phone,
        status: account.status,
        isMaster: false,
        organizationId: account.organization?.id ?? null,
        allBranches: account.all_branches,
        branchIds: apiBranches.map((b) => b.id),
      },
      role: account.role
        ? { ...account.role, permissions: account.permissions }
        : { name: 'Staff', permissions: account.permissions },
      org: account.organization || null,
      // The real authority: the server's effective permission list.
      can: makeCan(new Set(account.permissions || [])),
      branches: apiBranches,
      branchScope,
      apiBranches,
      apiBranchIds,
      activeBranchId,
      subscription: subscriptionState(account.organization),
    }
  }, [account, status, branchScope, login, logout, loginAs, loginWithQr,
      replaceAccount, refreshAccount])

  // Added on top rather than threaded through every branch above: whether the
  // server is currently unreachable, and a way to try again now.
  const session = useMemo(() => ({
    ...value,
    isOffline: status === 'offline',
    sessionAttempts: attempts,
    retrySession: restoreSession,
  }), [value, status, attempts, restoreSession])

  return <AuthCtx.Provider value={session}>{children}</AuthCtx.Provider>
}
