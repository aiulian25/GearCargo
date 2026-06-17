import { useEffect, lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import toast, { Toaster, useToasterStore } from 'react-hot-toast'
import { useAuth } from './contexts/AuthContext'
import { initializeSync } from './db'

// Layouts — eager: part of the app shell, needed immediately on every route.
import AppLayout from './layouts/AppLayout'
import AuthLayout from './layouts/AuthLayout'

// PWA Components — eager: tiny, mounted globally.
import { InstallPrompt, UpdatePrompt, PullToRefresh } from './components/PWA'

// Suspense fallback for lazily-loaded route chunks.
import PageLoader from './components/ui/PageLoader'

// ---------------------------------------------------------------------------
// Route-level code splitting (IMPROVEMENTS.md §2).
// Every page is loaded via React.lazy() so it ships as its own chunk fetched
// on demand, instead of being bundled into one ~1.7 MB entry. This drastically
// cuts the initial download (the login screen no longer pulls in the entire app,
// recharts, jspdf, etc.) — the biggest PWA first-load / Lighthouse win.
// ---------------------------------------------------------------------------

// Auth Pages
const Login = lazy(() => import('./pages/auth/Login'))
const Register = lazy(() => import('./pages/auth/Register'))
const ForgotPassword = lazy(() => import('./pages/auth/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/auth/ResetPassword'))
const ForcePasswordChange = lazy(() => import('./pages/auth/ForcePasswordChange'))
const SetupSecurityQuestions = lazy(() => import('./pages/auth/SetupSecurityQuestions'))
const VerifyEmail = lazy(() => import('./pages/auth/VerifyEmail'))

// Main Pages
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Vehicles = lazy(() => import('./pages/vehicles/Vehicles'))
const VehicleDetail = lazy(() => import('./pages/vehicles/VehicleDetail'))
const AddVehicle = lazy(() => import('./pages/vehicles/AddVehicle'))
const EditVehicle = lazy(() => import('./pages/vehicles/EditVehicle'))
const AddVehicleFuel = lazy(() => import('./pages/vehicles/AddVehicleFuel'))
const AddVehicleService = lazy(() => import('./pages/vehicles/AddVehicleService'))
const AddVehicleRepair = lazy(() => import('./pages/vehicles/AddVehicleRepair'))
const AddVehicleTax = lazy(() => import('./pages/vehicles/AddVehicleTax'))
const AddVehicleParking = lazy(() => import('./pages/vehicles/AddVehicleParking'))
const AddVehicleReminder = lazy(() => import('./pages/vehicles/AddVehicleReminder'))
const AddVehicleTodo = lazy(() => import('./pages/vehicles/AddVehicleTodo'))
const AddVehicleInsurance = lazy(() => import('./pages/vehicles/AddVehicleInsurance'))
const VehicleExpenses = lazy(() => import('./pages/vehicles/VehicleExpenses'))
const VehicleTimeline = lazy(() => import('./pages/vehicles/VehicleTimeline'))
const VehicleCharts = lazy(() => import('./pages/vehicles/VehicleCharts'))
const VehicleAlerts = lazy(() => import('./pages/vehicles/VehicleAlerts'))
const VehicleHealth = lazy(() => import('./pages/vehicles/VehicleHealth'))
const VehicleDocuments = lazy(() => import('./pages/vehicles/VehicleDocuments'))
const VehicleConsumables = lazy(() => import('./pages/vehicles/VehicleConsumables'))
const AddVehicleConsumable = lazy(() => import('./pages/vehicles/AddVehicleConsumable'))
const VehicleChat = lazy(() => import('./pages/vehicles/VehicleChat'))
const FuelEntries = lazy(() => import('./pages/fuel/FuelEntries'))
const AddFuel = lazy(() => import('./pages/fuel/AddFuel'))
const ShareTarget = lazy(() => import('./pages/ShareTarget'))
const Calendar = lazy(() => import('./pages/calendar/Calendar'))
const Services = lazy(() => import('./pages/services/Services'))
const AddService = lazy(() => import('./pages/services/AddService'))
const Repairs = lazy(() => import('./pages/repairs/Repairs'))
const AddRepair = lazy(() => import('./pages/repairs/AddRepair'))
const Reminders = lazy(() => import('./pages/reminders/Reminders'))
const AddReminder = lazy(() => import('./pages/reminders/AddReminder'))
const SmartRecommendations = lazy(() => import('./pages/predictions/SmartRecommendations'))
const Settings = lazy(() => import('./pages/settings/Settings'))
const Profile = lazy(() => import('./pages/settings/Profile'))
const Share = lazy(() => import('./pages/Share'))
const SharedReport = lazy(() => import('./pages/SharedReport'))

// Protected Route Component
const ProtectedRoute = ({ children, allowPasswordChange = false }) => {
  const { isAuthenticated, isLoading, user } = useAuth()
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent"></div>
      </div>
    )
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  // Force password change if required (except on the password change page itself)
  if (user?.must_change_password && !allowPasswordChange) {
    return <Navigate to="/change-password" replace />
  }
  
  return children
}

// Public Route (redirect to app if authenticated)
const PublicRoute = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth()
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--color-accent)] border-t-transparent"></div>
      </div>
    )
  }
  
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }
  
  return children
}

// Cap how many toasts are visible at once so a burst of notifications can't
// stack up and drown each other (UI/UX §2 — toast consolidation). The store
// lists newest-first, so we keep the most recent N and dismiss the rest.
const TOAST_LIMIT = 3
function useToastLimit() {
  const { toasts } = useToasterStore()
  useEffect(() => {
    toasts
      .filter((tt) => tt.visible)
      .filter((_, i) => i >= TOAST_LIMIT)
      .forEach((tt) => toast.dismiss(tt.id))
  }, [toasts])
}

function App() {
  useToastLimit()

  // Initialize offline sync on app startup
  useEffect(() => {
    initializeSync().catch(err => {
      console.error('Failed to initialize offline sync:', err)
    })
  }, [])

  return (
    <>
      {/* PWA Components */}
      <InstallPrompt />
      <UpdatePrompt />
      <PullToRefresh />
      
      <Toaster
        position="top-center"
        gutter={8}
        toastOptions={{
          duration: 3000,
          // Cap width so long (translated) messages wrap instead of overflowing.
          style: {
            background: 'var(--color-bg-card)',
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-border)',
            fontSize: '14px',
            padding: '12px 16px',
            maxWidth: '92vw',
          },
          success: {
            duration: 2500,
            iconTheme: {
              primary: '#22c55e',
              secondary: '#fff',
            },
          },
          // Errors linger longer than successes so they aren't missed/drowned.
          error: {
            duration: 5000,
            ariaProps: { role: 'alert', 'aria-live': 'assertive' },
            iconTheme: {
              primary: '#ef4444',
              secondary: '#fff',
            },
          },
        }}
      />
      
      <Suspense fallback={<PageLoader fullscreen />}>
      <Routes>
        {/* Auth Routes - Public only */}
        <Route path="/login" element={<AuthLayout><PublicRoute><Login /></PublicRoute></AuthLayout>} />
        <Route path="/register" element={<AuthLayout><PublicRoute><Register /></PublicRoute></AuthLayout>} />
        <Route path="/forgot-password" element={<AuthLayout><PublicRoute><ForgotPassword /></PublicRoute></AuthLayout>} />
        <Route path="/reset-password" element={<AuthLayout><PublicRoute><ResetPassword /></PublicRoute></AuthLayout>} />
        
        {/* Email Verification - Accessible when logged in or logged out */}
        <Route path="/verify-email" element={<VerifyEmail />} />

        {/* Public read-only shared report (F05) - no auth, accessible to anyone with the link */}
        <Route path="/shared/report/:token" element={<SharedReport />} />
        
        {/* Force Password Change - Protected but accessible when must_change_password is true */}
        <Route path="/change-password" element={<ProtectedRoute allowPasswordChange={true}><ForcePasswordChange /></ProtectedRoute>} />
        
        {/* Setup Security Questions - Protected, shown after first password change */}
        <Route path="/setup-security-questions" element={<ProtectedRoute><SetupSecurityQuestions /></ProtectedRoute>} />
        
        {/* Protected App Routes */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route index element={<Dashboard />} />
          
          {/* Vehicles */}
          <Route path="vehicles" element={<Vehicles />} />
          <Route path="vehicles/add" element={<AddVehicle />} />
          <Route path="vehicles/:id" element={<VehicleDetail />} />
          <Route path="vehicles/:id/edit" element={<EditVehicle />} />
          <Route path="vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
          <Route path="vehicles/:id/service/add" element={<AddVehicleService />} />
          <Route path="vehicles/:id/repair/add" element={<AddVehicleRepair />} />
          <Route path="vehicles/:id/tax/add" element={<AddVehicleTax />} />
          <Route path="vehicles/:id/parking/add" element={<AddVehicleParking />} />
          <Route path="vehicles/:id/reminder/add" element={<AddVehicleReminder />} />
          <Route path="vehicles/:id/todo/add" element={<AddVehicleTodo />} />
          <Route path="vehicles/:id/insurance/add" element={<AddVehicleInsurance />} />
          <Route path="vehicles/:id/consumables" element={<VehicleConsumables />} />
          <Route path="vehicles/:id/consumable/add" element={<AddVehicleConsumable />} />
          <Route path="vehicles/:id/chat" element={<VehicleChat />} />
          <Route path="vehicles/:id/expenses" element={<VehicleExpenses />} />
          <Route path="vehicles/:id/timeline" element={<VehicleTimeline />} />
          <Route path="vehicles/:id/charts" element={<VehicleCharts />} />
          <Route path="vehicles/:id/alerts" element={<VehicleAlerts />} />
          <Route path="vehicles/:id/health" element={<VehicleHealth />} />
          <Route path="vehicles/:id/search" element={<VehicleDocuments />} />
          
          {/* Calendar */}
          <Route path="calendar" element={<Calendar />} />
          
          {/* Fuel */}
          <Route path="fuel" element={<FuelEntries />} />
          <Route path="fuel/add" element={<AddFuel />} />

          {/* Web Share Target — receipt shared from the OS share sheet */}
          <Route path="share-target" element={<ShareTarget />} />
          
          {/* Services */}
          <Route path="services" element={<Services />} />
          <Route path="services/add" element={<AddService />} />
          
          {/* Repairs */}
          <Route path="repairs" element={<Repairs />} />
          <Route path="repairs/add" element={<AddRepair />} />
          
          {/* Reminders */}
          <Route path="reminders" element={<Reminders />} />
          <Route path="reminders/add" element={<AddReminder />} />
          
          {/* Smart Recommendations */}
          <Route path="recommendations" element={<SmartRecommendations />} />
          
          {/* Settings */}
          <Route path="settings" element={<Settings />} />
          <Route path="settings/profile" element={<Profile />} />
          
          {/* Share Target */}
          <Route path="share" element={<Share />} />
        </Route>
        
        {/* Catch all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
    </>
  )
}

export default App
