import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import { useBackgroundSync } from '../src/hooks/useBackgroundSync'
import AddVehicleFuel from '../src/pages/vehicles/AddVehicleFuel'
import SyncIndicator from '../src/components/PWA/SyncIndicator'
import api, { attachmentApi } from '../src/services/api'
import { receiptUploadKey } from '../src/utils/receiptProtocol'
import { getBoundIdentity } from '../src/utils/offlineIdentity'
import { mutationOptions } from '../src/utils/mutationProtocol'
import { saveExpenseWithReceipt } from '../src/utils/receiptExpense'
export default function Harness() {
  const auth = useAuth(), sync = useBackgroundSync()
  useEffect(() => { window.gc007 = { auth, api, mutationOptions }; window.gc010 = { save: saveExpenseWithReceipt, sync, attachmentApi, receiptUploadKey, getBoundIdentity } }, [auth, sync])
  return <><Toaster /><SyncIndicator variant="card" />{auth.isAuthenticated && <Routes><Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} /><Route path="*" element={<p>{auth.user?.username || 'Signed out'}</p>} /></Routes>}</>
}
const fuel = new URL(location.href).searchParams.get('fuel')
history.replaceState(null, '', fuel ? `/vehicles/${fuel}/fuel/add` : '/login')
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>)
