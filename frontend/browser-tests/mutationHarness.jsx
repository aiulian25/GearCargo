// Test-only shell around the production form, auth provider and API client.
import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import EditVehicle from '../src/pages/vehicles/EditVehicle'
import api from '../src/services/api'
import { mutationOptions } from '../src/utils/mutationProtocol'

export default function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc007 = { auth, api, mutationOptions } }, [auth])
  return <><Toaster /><Routes>
    <Route path="/vehicles/:id/edit" element={<EditVehicle />} />
    <Route path="*" element={<p>{auth.isLoading ? 'Loading' : auth.user?.username || 'Signed out'}</p>} />
  </Routes></>
}

const edit = new URL(location.href).searchParams.get('edit')
history.replaceState(null, '', edit ? `/vehicles/${edit}/edit` : '/login')
createRoot(document.getElementById('root')).render(
  <BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>
)
