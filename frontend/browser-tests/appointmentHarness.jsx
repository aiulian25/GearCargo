import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import { ConfirmProvider } from '../src/components/ui/ConfirmDialog'
import VehicleAppointments from '../src/pages/vehicles/VehicleAppointments'
import AddVehicleService from '../src/pages/vehicles/AddVehicleService'
import { mutationDb } from '../src/db/mutationQueue'
import api from '../src/services/api'
function Harness() {
  const auth = useAuth()
  useEffect(() => { window.appointmentFixture = { auth, api, mutationDb } }, [auth])
  return auth.isAuthenticated && <Routes>
    <Route path="/vehicles/:id/appointments" element={<VehicleAppointments />} />
    <Route path="/vehicles/:id/service/add" element={<AddVehicleService />} />
    <Route path="*" element={<p>Appointment fixture</p>} />
  </Routes>
}
history.replaceState(null, '', '/login')
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><ConfirmProvider><Harness /></ConfirmProvider></AuthProvider></LanguageProvider></BrowserRouter>)
