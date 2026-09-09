/**
 * Subscription state, derived from what /auth/me returns.
 *
 * The previous version of this module computed usage and enforced plan limits
 * in the browser against the demo store. Both are gone: usage now comes from
 * the API, and limits are enforced by `SubscriptionLimitService` on the server
 * before the INSERT. A limit check in the browser was only ever a hint, and
 * keeping one invites the belief that it is the thing protecting the plan.
 */

/** How close to expiry before the shell starts warning. */
const EXPIRY_WARNING_DAYS = 30

/**
 * Normalises the API's subscription summary into what the shell displays.
 * `organization` is the object from /auth/me, with `subscription` nested.
 */
export function subscriptionState(organization) {
  if (!organization) return null

  const status = String(organization.status || '').toUpperCase()
  if (status === 'SUSPENDED') return { label: 'Suspended', days: 0, tone: 'rose' }
  if (status === 'CANCELLED') return { label: 'Cancelled', days: 0, tone: 'slate' }

  const sub = organization.subscription
  if (!sub) return { label: 'No subscription', days: 0, tone: 'slate' }

  const days = sub.days_remaining ?? 0
  const subStatus = String(sub.status || '').toUpperCase()

  if (days < 0 || subStatus === 'EXPIRED') return { label: 'Expired', days, tone: 'rose' }
  if (subStatus === 'TRIAL') return { label: 'Trial', days, tone: 'blue' }
  if (subStatus === 'GRACE') return { label: 'Expiring soon', days, tone: 'amber' }
  if (days <= EXPIRY_WARNING_DAYS) return { label: 'Expiring soon', days, tone: 'amber' }
  return { label: 'Active', days, tone: 'emerald' }
}
