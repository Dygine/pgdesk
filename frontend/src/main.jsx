import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { router } from '@/routes'
import { initNative } from '@/native/android'
import { markHealthy } from '@/lib/liveUpdate'
import './index.css'

/* No-op on the web; wires the back button, status bar and keyboard on Android.
   Fire-and-forget: a failure in an optional native nicety must never stop the
   application from rendering. */
initNative(router).catch((e) => console.warn('native init skipped:', e))

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

/* Tell the live updater this bundle starts.
   This MUST happen here rather than inside a component. It used to live in
   UpdateBanner, which renders inside AppShell - and AppShell only mounts once
   somebody is signed in. So on the login screen it never ran, the updater hit
   its appReadyTimeout, concluded the bundle was broken and reloaded the app.
   The result was a launch that looped on "Restoring your session" forever and
   could never reach a login form.
   Deliberately after render() so a bundle that fails to parse or load a chunk
   never gets here and is still rolled back. It does not catch a bundle that
   mounts and then crashes later, which is the trade for having the app
   reachable at all when signed out. */
markHealthy().catch(() => {})
