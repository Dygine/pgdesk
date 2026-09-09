/**
 * Android host behaviour.
 *
 * Everything here is a no-op on the web, so it can be imported unconditionally
 * from main.jsx and there is no second code path to keep in sync.
 *
 * Scope is deliberately small. PGDesk is a web application in a WebView; the
 * only native concerns are the ones a WebView genuinely cannot express:
 * the hardware back button, the status bar, and the keyboard.
 */
import { Capacitor } from '@capacitor/core'

/** Routes where "back" should exit rather than navigate. */
const PORTAL_ROOTS = new Set(['/app', '/master', '/me', '/login'])

export async function initNative(router) {
  if (!Capacitor.isNativePlatform()) return

  const [{ App }, { StatusBar, Style }, { Keyboard }] = await Promise.all([
    import('@capacitor/app'),
    import('@capacitor/status-bar'),
    import('@capacitor/keyboard'),
  ])

  /* ---------------------------------------------------------- status bar */
  try {
    await StatusBar.setStyle({ style: Style.Light })
    await StatusBar.setBackgroundColor({ color: '#0F172A' })
    // Do not overlay: the app shell already owns the full viewport, and an
    // overlaid bar would sit on top of the sticky topbar.
    await StatusBar.setOverlaysWebView({ overlay: false })
  } catch { /* some OEM skins reject these; not worth failing startup over */ }

  /* ------------------------------------------------------------ keyboard */
  // Tell the layout when the keyboard is up so a fixed bottom nav can get out
  // of the way instead of floating over the field being typed into.
  Keyboard.addListener('keyboardWillShow', (info) => {
    document.documentElement.style.setProperty('--kb-height', `${info.keyboardHeight}px`)
    document.body.classList.add('kb-open')
  })
  Keyboard.addListener('keyboardWillHide', () => {
    document.documentElement.style.setProperty('--kb-height', '0px')
    document.body.classList.remove('kb-open')
  })

  /* --------------------------------------------------------- back button */
  App.addListener('backButton', ({ canGoBack }) => {
    // An open dialog is what the user means to dismiss, not the page.
    const dialog = document.querySelector('[role="dialog"], [data-modal-open="true"]')
    if (dialog) {
      const close = dialog.querySelector('[data-modal-close], [aria-label="Close"]')
      if (close) { close.click(); return }
    }

    const path = window.location.pathname.replace(/\/$/, '')
    if (PORTAL_ROOTS.has(path) || !canGoBack) {
      App.exitApp()
      return
    }
    router ? router.navigate(-1) : window.history.back()
  })

  /* ------------------------------------------------------------ lifecycle */
  App.addListener('appStateChange', ({ isActive }) => {
    if (!isActive) return
    // Coming back from the background after a while, the 30-minute access token
    // is usually stale. Nudging the app to revalidate here means the user sees
    // fresh data rather than a burst of 401-then-retry on their first tap.
    window.dispatchEvent(new CustomEvent('pgdesk:resume'))
  })
}
