/**
 * Razorpay Checkout, loaded on demand.
 *
 * The script is fetched only when a resident actually taps "Pay online", so
 * nobody else downloads it. It runs inside the Android WebView as it does in a
 * browser - no native plugin, so no new APK was needed for this.
 *
 * `openCheckout` resolves with Razorpay's three ids on success and rejects with
 * an Error whose `.dismissed` is true when the resident closed the sheet. The
 * ids prove nothing on their own: the caller must send them to the API, which
 * checks the signature with the PG's secret before recording anything.
 */
const SRC = 'https://checkout.razorpay.com/v1/checkout.js'
let loading = null

function loadScript() {
  if (window.Razorpay) return Promise.resolve()
  if (loading) return loading
  loading = new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = SRC
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => { loading = null; reject(new Error('Could not load Razorpay. Check your internet connection.')) }
    document.head.appendChild(s)
  })
  return loading
}

export async function openCheckout(order) {
  await loadScript()
  return new Promise((resolve, reject) => {
    const rzp = new window.Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount_paise,
      currency: order.currency || 'INR',
      name: order.name,
      description: order.description,
      prefill: order.prefill || {},
      theme: { color: '#2C3182' },
      handler: (res) => resolve(res),
      modal: {
        ondismiss: () => {
          const err = new Error('Payment was not completed.')
          err.dismissed = true
          reject(err)
        },
      },
    })
    rzp.on('payment.failed', (res) => {
      reject(new Error(res?.error?.description || 'The payment failed. No money was taken.'))
    })
    rzp.open()
  })
}

/** The standard UPI deep link. Any UPI app on the phone can open it. */
export function upiLink({ upiId, payee, amount, note }) {
  const params = new URLSearchParams({ pa: upiId, pn: payee || '', cu: 'INR' })
  if (amount) params.set('am', Number(amount).toFixed(2))
  if (note) params.set('tn', note.slice(0, 50))
  return `upi://pay?${params.toString()}`
}
