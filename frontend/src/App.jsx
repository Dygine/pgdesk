import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ToastProvider } from '@/context/ToastContext'
import { router } from '@/routes'
import { LegacyDomainBanner } from '@/components/domain'

/**
 * Auth resolves the session from the API and every page reads it from there.
 * Toast sits inside so any page — including the ones Auth renders while it is
 * still resolving — can raise a message.
 */
export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        {/* Above the router, so it shows on every screen including login. It
            renders nothing except inside an app still loading from a retired
            domain - see LegacyDomainBanner. */}
        <LegacyDomainBanner />
        <RouterProvider router={router} />
      </ToastProvider>
    </AuthProvider>
  )
}
