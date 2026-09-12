import { useEffect, useState } from 'react'
import { createBrowserRouter, Navigate, Outlet, useLocation, Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { AppShell, SubscriptionBanner } from '@/components/layout/AppShell'
import { RouteGuard } from '@/components/domain'
import { ORG_NAV, MASTER_NAV, CUSTOMER_NAV, BOTTOM_NAV, filterNav } from '@/nav/navConfig'
import { Skeleton, Button, EmptyState, Card } from '@/components/ui'

import Login from '@/pages/auth/Login'
import ForgotPassword from '@/pages/auth/ForgotPassword'
import Signup from '@/pages/auth/Signup'
import FindPG from '@/pages/public/FindPG'
import SiteLayout from '@/components/site/SiteLayout'
import Home from '@/pages/site/Home'
import SiteFeatures from '@/pages/site/Features'
import SitePricing from '@/pages/site/Pricing'
import SiteFaq from '@/pages/site/Faq'
import SiteContact from '@/pages/site/Contact'
import Enquiries from '@/pages/org/Enquiries'

/* Master portal */
import MasterDashboard from '@/pages/master/MasterDashboard'
import Organizations from '@/pages/master/Organizations'
import CreateOrgWizard from '@/pages/master/CreateOrgWizard'
import OrganizationDetail from '@/pages/master/OrganizationDetail'
import Subscriptions from '@/pages/master/Subscriptions'
import Usage from '@/pages/master/Usage'
import MasterAudit from '@/pages/master/MasterAudit'
import MasterSettings from '@/pages/master/MasterSettings'
import MasterWebsite from '@/pages/master/MasterWebsite'

/* Org portal */
import OwnerDashboard from '@/pages/org/OwnerDashboard'
import Branches from '@/pages/org/Branches'
import Blueprint from '@/pages/org/Blueprint'
import Property from '@/pages/org/Property'
import Rooms from '@/pages/org/Rooms'
import Beds from '@/pages/org/Beds'
import Residents from '@/pages/org/Residents'
import ResidentProfile from '@/pages/org/ResidentProfile'
import CheckIn from '@/pages/org/CheckIn'
import Transfer from '@/pages/org/Transfer'
import Checkout from '@/pages/org/Checkout'
import Invoices from '@/pages/org/Invoices'
import Payments from '@/pages/org/Payments'
import Expenses from '@/pages/org/Expenses'
import Accounts from '@/pages/org/Accounts'
import Complaints from '@/pages/org/Complaints'
import Attendance from '@/pages/org/Attendance'
import Scan from '@/pages/org/Scan'
import Food from '@/pages/org/Food'
import Laundry from '@/pages/org/Laundry'
import Visitors from '@/pages/org/Visitors'
import GatePasses from '@/pages/org/GatePasses'
import Announcements from '@/pages/org/Announcements'
import Queries from '@/pages/org/Queries'
import Staff from '@/pages/org/Staff'
import Users from '@/pages/org/Users'
import Roles from '@/pages/org/Roles'
import Inventory from '@/pages/org/Inventory'
import Assets from '@/pages/org/Assets'
import Reports from '@/pages/org/Reports'
import Audit from '@/pages/org/Audit'
import Settings from '@/pages/org/Settings'

/* Resident portal */
import MyHome from '@/pages/customer/MyHome'
import MyRent from '@/pages/customer/MyRent'
import MyFood from '@/pages/customer/MyFood'
import MyAttendance from '@/pages/customer/MyAttendance'
import MyScan from '@/pages/customer/MyScan'
import MyComplaints from '@/pages/customer/MyComplaints'
import MyLaundry from '@/pages/customer/MyLaundry'
import MyMoveOut from '@/pages/customer/MyMoveOut'
import { MyGatePass, MyVisitors, MyQueries } from '@/pages/customer/MyRequests'
import { MyAnnouncements, MyProfile } from '@/pages/customer/MyAccount'

/**
 * Three shells, one component. Each portal supplies its own nav data; AppShell
 * renders sidebar + drawer + bottom bar from it. Nothing is duplicated per
 * breakpoint — the same NavList drives desktop and mobile.
 */

/**
 * Shown while the session is being restored, so a reload does not flash the
 * login page - and, when the server cannot be reached, instead of the login
 * page. A deploy or a sleeping free-tier server is not a reason to make anyone
 * sign in again; their login is kept and this screen retries on its own.
 */
function SessionLoading() {
  const { isOffline, retrySession, sessionAttempts } = useAuth() || {}
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 8000)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
      <div className="max-w-sm w-full flex flex-col items-center text-center gap-3">
        <img src="/pgguru-logo.png" alt="PGuru" className="w-[320px] max-w-[85%] h-auto animate-pulse" />
        {!isOffline ? (
          <>
            <p className="text-sm text-slate-500">Restoring your session…</p>
            {slow && (
              <p className="text-xs text-slate-400 leading-relaxed">
                The server was asleep and is waking up. The first open of the day can take up to a minute.
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-base font-semibold text-slate-900">Connecting to PGuru…</p>
            <p className="text-sm text-slate-600 leading-relaxed">
              The server is starting up or your internet dropped. If you were signed in,
              you stay signed in - this screen continues by itself once it connects.
            </p>
            <Button variant="primary" onClick={() => retrySession?.()}>Try now</Button>
            <p className="text-2xs text-slate-400 tnum">Attempt {sessionAttempts || 1}</p>
          </>
        )}
      </div>
    </div>
  )
}

function RequirePortal({ portal }) {
  const { can, portal: current, isAuthenticated, isLoading, isOffline } = useAuth()
  const location = useLocation()

  // The refresh token outlives the page, so we must wait for /auth/me to answer
  // before deciding anyone is anonymous.
  // An unreachable server is not an answer either: it waits on the same
  // screen, which retries by itself, rather than showing the login form.
  if (isLoading || isOffline) return <SessionLoading />

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (current !== portal) {
    const home = { master: '/master', org: '/app', customer: '/me' }[current] || '/login'
    return <Navigate to={home} replace />
  }

  if (portal === 'master') {
    return (
      <AppShell navGroups={filterNav(MASTER_NAV, can)} bottomItems={BOTTOM_NAV.master}
        showBranchSelector={false}>
        <Outlet />
      </AppShell>
    )
  }
  if (portal === 'customer') {
    return (
      <AppShell navGroups={CUSTOMER_NAV} bottomItems={BOTTOM_NAV.customer}
        showBranchSelector={false} showSearch={false}>
        <Outlet />
      </AppShell>
    )
  }
  return (
    <AppShell navGroups={filterNav(ORG_NAV, can)}
      bottomItems={BOTTOM_NAV.org.filter((i) => !i.perm || can(i.perm))}
      banner={<SubscriptionBanner />}>
      <Outlet />
    </AppShell>
  )
}

/** Wraps a page in its permission requirement. Missing it renders 403, not a redirect. */
const guard = (perm, element) => <RouteGuard perm={perm}>{element}</RouteGuard>

function RootRedirect() {
  const { portal, isLoading, isOffline } = useAuth()
  if (isLoading || isOffline) return <SessionLoading />
  return <Navigate to={{ master: '/master', org: '/app', customer: '/me' }[portal] || '/login'} replace />
}

/** Someone already signed in has no reason to see the login form. */
function LoginRoute() {
  const { portal, isAuthenticated, isLoading, isOffline } = useAuth()
  if (isLoading || isOffline) return <SessionLoading />
  if (isAuthenticated) {
    return <Navigate to={{ master: '/master', org: '/app', customer: '/me' }[portal] || '/'} replace />
  }
  return <Login />
}

function NotFound() {
  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
      <Card className="max-w-md w-full">
        <EmptyState title="Page not found"
          message="That address does not exist in this demo. It may have been a link from an older build."
          action={<Link to="/"><Button variant="primary">Go back</Button></Link>} />
      </Card>
    </div>
  )
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginRoute /> },
  // Public: someone who cannot sign in obviously cannot be behind a guard.
  { path: '/forgot-password', element: <ForgotPassword /> },
  { path: '/signup', element: <Signup /> },
  // Deliberately reachable without a session. Someone hunting for a PG has no
  // account and will not make one to browse - putting this behind a login would
  // mean nobody ever sees a listing.
  { path: '/find-pg', element: <FindPG /> },
  // The public website. Several pages sharing one layout, which fetches the
  // content once - so moving between them is instant and makes no request.
  // Everyone lands here, signed in or not: this is the front door of the
  // product, not a redirect on the way to a dashboard.
  {
    path: '/',
    element: <SiteLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'features', element: <SiteFeatures /> },
      { path: 'pricing', element: <SitePricing /> },
      { path: 'faq', element: <SiteFaq /> },
      { path: 'contact', element: <SiteContact /> },
    ],
  },

  {
    path: '/master',
    element: <RequirePortal portal="master" />,
    children: [
      { index: true, element: guard('master.dashboard', <MasterDashboard />) },
      { path: 'organizations', element: guard('master.organizations', <Organizations />) },
      { path: 'organizations/new', element: guard('master.organizations', <CreateOrgWizard />) },
      { path: 'organizations/:id', element: guard('master.organizations', <OrganizationDetail />) },
      { path: 'subscriptions', element: guard('master.subscriptions', <Subscriptions />) },
      { path: 'usage', element: guard('master.usage', <Usage />) },
      { path: 'audit', element: guard('master.audit', <MasterAudit />) },
      { path: 'website', element: guard('master.settings', <MasterWebsite />) },
      { path: 'settings', element: guard('master.settings', <MasterSettings />) },
    ],
  },

  {
    path: '/app',
    element: <RequirePortal portal="org" />,
    children: [
      { index: true, element: guard('dashboard.view', <OwnerDashboard />) },
      { path: 'branches', element: guard('branches.view', <Branches />) },
      { path: 'blueprint', element: guard('rooms.view', <Blueprint />) },
      { path: 'property', element: guard('property.view', <Property />) },
      { path: 'rooms', element: guard('rooms.view', <Rooms />) },
      { path: 'beds', element: guard('beds.view', <Beds />) },
      { path: 'residents', element: guard('customers.view', <Residents />) },
      { path: 'enquiries', element: guard('customers.view', <Enquiries />) },
      { path: 'residents/:id', element: guard('customers.view', <ResidentProfile />) },
      { path: 'check-in', element: guard('customers.checkin', <CheckIn />) },
      { path: 'transfer', element: guard('customers.transfer', <Transfer />) },
      { path: 'checkout', element: guard('customers.checkout', <Checkout />) },
      { path: 'invoices', element: guard('invoices.view', <Invoices />) },
      { path: 'payments', element: guard('payments.view', <Payments />) },
      { path: 'expenses', element: guard('expenses.view', <Expenses />) },
      { path: 'accounts', element: guard('reports.view', <Accounts />) },
      { path: 'complaints', element: guard('complaints.view', <Complaints />) },
      { path: 'attendance', element: guard('attendance.view', <Attendance />) },
      { path: 'scan', element: guard('attendance.mark', <Scan />) },
      { path: 'food', element: guard('food.view', <Food />) },
      { path: 'laundry', element: guard('laundry.view', <Laundry />) },
      { path: 'visitors', element: guard('visitors.view', <Visitors />) },
      { path: 'gate-passes', element: guard('gatepass.view', <GatePasses />) },
      { path: 'announcements', element: guard('announcements.view', <Announcements />) },
      { path: 'queries', element: guard('queries.view', <Queries />) },
      { path: 'staff', element: guard('staff.view', <Staff />) },
      { path: 'users', element: guard('users.view', <Users />) },
      { path: 'roles', element: guard('roles.view', <Roles />) },
      { path: 'inventory', element: guard('inventory.view', <Inventory />) },
      { path: 'assets', element: guard('assets.view', <Assets />) },
      { path: 'reports', element: guard('reports.view', <Reports />) },
      { path: 'audit', element: guard('audit.view', <Audit />) },
      { path: 'settings', element: guard('settings.view', <Settings />) },
    ],
  },

  {
    path: '/me',
    element: <RequirePortal portal="customer" />,
    children: [
      { index: true, element: <MyHome /> },
      { path: 'rent', element: <MyRent /> },
      { path: 'food', element: <MyFood /> },
      { path: 'attendance', element: <MyAttendance /> },
      { path: 'scan', element: <MyScan /> },
      { path: 'laundry', element: <MyLaundry /> },
      { path: 'complaints', element: <MyComplaints /> },
      { path: 'visitors', element: <MyVisitors /> },
      { path: 'gate-pass', element: <MyGatePass /> },
      { path: 'queries', element: <MyQueries /> },
      { path: 'announcements', element: <MyAnnouncements /> },
      { path: 'moving-out', element: <MyMoveOut /> },
      { path: 'profile', element: <MyProfile /> },
    ],
  },

  { path: '*', element: <NotFound /> },
])
