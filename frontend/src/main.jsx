import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { router } from '@/routes'
import { initNative } from '@/native/android'
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
