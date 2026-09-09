import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ToastProvider } from '@/context/ToastContext'
import { router } from '@/routes'

/**
 * Auth resolves the session from the API and every page reads it from there.
 * Toast sits inside so any page — including the ones Auth renders while it is
 * still resolving — can raise a message.
 */
export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </AuthProvider>
  )
}
