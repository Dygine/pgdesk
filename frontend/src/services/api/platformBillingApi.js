/**
 * What a PG owner pays PGuru, and the operator's side of it.
 *
 * Separate from `invoiceApi` and `paymentApi`, which are residents paying their
 * landlord. These two money flows never meet: this one settles through Dygine
 * Pay into the platform's account, that one through each owner's own Razorpay
 * keys. Keeping the API modules apart keeps the distinction visible in the UI
 * code as well as the backend.
 */
import { api, unwrap } from './client'

export const platformBillingApi = {
  // --- the owner's own billing ---
  summary: () => api.get('/billing/platform/summary').then(unwrap),
  history: (limit = 50) =>
    api.get('/billing/platform/history', { limit }).then(unwrap),
  walletTransactions: () =>
    api.get('/billing/platform/wallet/transactions').then(unwrap),

  /** Price a coupon without reserving it, so the owner sees the new total. */
  previewCoupon: (code) =>
    api.post('/billing/platform/coupons/preview', { code }).then(unwrap),

  topup: (amountRupees) =>
    api.post('/billing/platform/topup', { amount_rupees: amountRupees }).then(unwrap),

  /** Returns a checkout_url to redirect to. */
  subscriptionCheckout: (body) =>
    api.post('/billing/platform/subscription/checkout', body).then(unwrap),

  /** Settles immediately. A 409 means the balance does not cover it. */
  payFromWallet: (body) =>
    api.post('/billing/platform/subscription/pay-from-wallet', body).then(unwrap),

  setAutoDebit: (enabled) =>
    api.post('/billing/platform/auto-debit', { enabled }).then(unwrap),
}

export const couponApi = {
  list: () => api.get('/master/coupons').then(unwrap),
  create: (body) => api.post('/master/coupons', body).then(unwrap),
  update: (id, body) => api.patch(`/master/coupons/${id}`, body).then(unwrap),
  remove: (id) => api.delete(`/master/coupons/${id}`).then(unwrap),
  assign: (id, organizationIds, notify = true) =>
    api.post(`/master/coupons/${id}/assign`, {
      organization_ids: organizationIds, notify,
    }).then(unwrap),
  unassign: (id, organizationId) =>
    api.delete(`/master/coupons/${id}/assign/${organizationId}`).then(unwrap),
  redemptions: (id) => api.get(`/master/coupons/${id}/redemptions`).then(unwrap),
}

export const platformRevenueApi = {
  revenue: (days = 90) => api.get('/master/revenue', { days }).then(unwrap),
  charges: (params) => api.get('/master/billing/charges', params).then(unwrap),
  /** Ask Dygine what happened to charges we never got an answer about. */
  reconcile: () => api.post('/master/billing/reconcile').then(unwrap),
  verifyDygine: () => api.post('/master/billing/verify-dygine').then(unwrap),
}
