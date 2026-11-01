import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import AddVehicleReminder from '../src/pages/vehicles/AddVehicleReminder'
import Reminders from '../src/pages/reminders/Reminders'
import api from '../src/services/api'

export default function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc021 = { auth, api } }, [auth])
  return auth.isAuthenticated && <Routes>
    <Route path="/vehicles/:id/reminder/add" element={<AddVehicleReminder />} />
    <Route path="/reminders" element={<Reminders />} />
    <Route path="*" element={<p>Reminder fixture</p>} />
  </Routes>
}
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>)
