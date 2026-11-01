import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import AddVehicleFuel from '../src/pages/vehicles/AddVehicleFuel'
import EditVehicle from '../src/pages/vehicles/EditVehicle'
import Profile from '../src/pages/settings/Profile'
import BackupSettings from '../src/components/settings/BackupSettings'
import api from '../src/services/api'
export default function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc015 = { auth, api } }, [auth])
  return <><Toaster />{auth.isAuthenticated && <Routes>
    <Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
    <Route path="/vehicles/:id/edit" element={<EditVehicle />} />
    <Route path="/profile" element={<Profile />} />
    <Route path="/backup" element={<BackupSettings />} />
    <Route path="*" element={<p>Unit fixture</p>} />
  </Routes>}</>
}
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>)
