import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { useAuth } from './contexts/AuthContext'
import { initializeSync } from './db'

// Layouts
import AppLayout from './layouts/AppLayout'
import AuthLayout from './layouts/AuthLayout'

// PWA Components
import { InstallPrompt, UpdatePrompt, PullToRefresh } from './components/PWA'

// Auth Pages
import Login from './pages/auth/Login'
import Register from './pages/auth/Register'
import ForgotPassword from './pages/auth/ForgotPassword'
import ResetPassword from './pages/auth/ResetPassword'
import ForcePasswordChange from './pages/auth/ForcePasswordChange'
import SetupSecurityQuestions from './pages/auth/SetupSecurityQuestions'
import VerifyEmail from './pages/auth/VerifyEmail'

// Main Pages
import Dashboard from './pages/Dashboard'
import Vehicles from './pages/vehicles/Vehicles'
import VehicleDetail from './pages/vehicles/VehicleDetail'
import AddVehicle from './pages/vehicles/AddVehicle'
import EditVehicle from './pages/vehicles/EditVehicle'
import AddVehicleFuel from './pages/vehicles/AddVehicleFuel'
import AddVehicleService from './pages/vehicles/AddVehicleService'
import AddVehicleRepair from './pages/vehicles/AddVehicleRepair'
import AddVehicleTax from './pages/vehicles/AddVehicleTax'
import AddVehicleParking from './pages/vehicles/AddVehicleParking'
import AddVehicleReminder from './pages/vehicles/AddVehicleReminder'
import AddVehicleTodo from './pages/vehicles/AddVehicleTodo'
import AddVehicleInsurance from './pages/vehicles/AddVehicleInsurance'
import VehicleExpenses from './pages/vehicles/VehicleExpenses'
import VehicleTimeline from './pages/vehicles/VehicleTimeline'
import VehicleCharts from './pages/vehicles/VehicleCharts'
import VehicleAlerts from './pages/vehicles/VehicleAlerts'
import VehicleHealth from './pages/vehicles/VehicleHealth'
import FuelEntries from './pages/fuel/FuelEntries'
import AddFuel from './pages/fuel/AddFuel'
import Calendar from './pages/calendar/Calendar'
import Services from './pages/services/Services'
import AddService from './pages/services/AddService'
import Repairs from './pages/repairs/Repairs'
import AddRepair from './pages/repairs/AddRepair'
import Reminders from './pages/reminders/Reminders'
import AddReminder from './pages/reminders/AddReminder'
import SmartRecommendations from './pages/predictions/SmartRecommendations'
import Settings from './pages/settings/Settings'
import Profile from './pages/settings/Profile'
import Share from './pages/Share'

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

function App() {
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
        toastOptions={{
          duration: 3000,
          style: {
            background: 'var(--color-bg-card)',
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-border)',
            fontSize: '14px',
            padding: '12px 16px',
          },
          success: {
            iconTheme: {
              primary: '#22c55e',
              secondary: '#fff',
            },
          },
          error: {
            iconTheme: {
              primary: '#ef4444',
              secondary: '#fff',
            },
          },
        }}
      />
      
      <Routes>
        {/* Auth Routes - Public only */}
        <Route path="/login" element={<AuthLayout><PublicRoute><Login /></PublicRoute></AuthLayout>} />
        <Route path="/register" element={<AuthLayout><PublicRoute><Register /></PublicRoute></AuthLayout>} />
        <Route path="/forgot-password" element={<AuthLayout><PublicRoute><ForgotPassword /></PublicRoute></AuthLayout>} />
        <Route path="/reset-password" element={<AuthLayout><PublicRoute><ResetPassword /></PublicRoute></AuthLayout>} />
        
        {/* Email Verification - Accessible when logged in or logged out */}
        <Route path="/verify-email" element={<VerifyEmail />} />
        
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
          <Route path="vehicles/:id/expenses" element={<VehicleExpenses />} />
          <Route path="vehicles/:id/timeline" element={<VehicleTimeline />} />
          <Route path="vehicles/:id/charts" element={<VehicleCharts />} />
          <Route path="vehicles/:id/alerts" element={<VehicleAlerts />} />
          <Route path="vehicles/:id/health" element={<VehicleHealth />} />
          
          {/* Calendar */}
          <Route path="calendar" element={<Calendar />} />
          
          {/* Fuel */}
          <Route path="fuel" element={<FuelEntries />} />
          <Route path="fuel/add" element={<AddFuel />} />
          
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
    </>
  )
}

export default App
