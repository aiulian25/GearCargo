import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import { ConfirmProvider } from '../src/components/ui/ConfirmDialog'
import VehicleTires from '../src/pages/vehicles/VehicleTires'
import AddVehicleReminder from '../src/pages/vehicles/AddVehicleReminder'
import { mutationDb } from '../src/db/mutationQueue'
import api from '../src/services/api'
function Harness() {
  const auth = useAuth()
  useEffect(() => { window.tireFixture = { auth, api, mutationDb } }, [auth])
  return auth.isAuthenticated && <Routes>
    <Route path="/vehicles/:id/tires" element={<VehicleTires />} />
    <Route path="/vehicles/:id/reminder/add" element={<AddVehicleReminder />} />
    <Route path="*" element={<p>Tire fixture</p>} />
  </Routes>
}
history.replaceState(null, '', '/login')
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><ConfirmProvider><Harness /></ConfirmProvider></AuthProvider></LanguageProvider></BrowserRouter>)
