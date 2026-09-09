import { ALL_PERMISSIONS } from '@/data/permissions'

export const WILDCARD = '*'

/** Expand a role's stored permission list; '*' means everything in the tenant namespace. */
export function expand(permissions = []) {
  if (permissions.includes(WILDCARD)) return new Set(ALL_PERMISSIONS)
  const out = new Set()
  for (const p of permissions) {
    if (p.endsWith('.*')) {
      const mod = p.slice(0, -2)
      ALL_PERMISSIONS.filter((x) => x.startsWith(`${mod}.`)).forEach((x) => out.add(x))
    } else out.add(p)
  }
  return out
}

/**
 * The one function every guard, nav item and button asks.
 * `perm` may be a string, an array (OR), or undefined (always allowed).
 */
export function makeCan(permissionSet) {
  return function can(perm) {
    if (!perm) return true
    if (Array.isArray(perm)) return perm.some((p) => permissionSet.has(p))
    return permissionSet.has(perm)
  }
}

/** Branch visibility. Owners see every branch in their org; staff see only assigned ones. */
export function visibleBranchIds(user, branches) {
  if (!user) return []
  const orgBranches = branches.filter((b) => b.organizationId === user.organizationId)
  if (user.allBranches) return orgBranches.map((b) => b.id)
  return orgBranches.filter((b) => (user.branchIds || []).includes(b.id)).map((b) => b.id)
}
