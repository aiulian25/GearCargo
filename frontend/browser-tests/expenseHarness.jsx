// GC-020: actual pages and edit form, independently bundled for browser checks.
import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import VehicleExpenses from '../src/pages/vehicles/VehicleExpenses'
import VehicleCharts from '../src/pages/vehicles/VehicleCharts'
import AddVehicleFuel from '../src/pages/vehicles/AddVehicleFuel'
import api from '../src/services/api'

export default function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc020 = { auth, api } }, [auth])
  return auth.isAuthenticated && <Routes>
    <Route path="/vehicles/:id/expenses" element={<VehicleExpenses />} />
    <Route path="/vehicles/:id/charts" element={<VehicleCharts />} />
    <Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
    <Route path="*" element={<p>Expense fixture</p>} />
  </Routes>
}

createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>)
