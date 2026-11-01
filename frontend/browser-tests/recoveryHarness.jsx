import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import { LanguageProvider } from '../src/contexts/LanguageContext'
import { useBackgroundSync } from '../src/hooks/useBackgroundSync'
import SyncIndicator from '../src/components/PWA/SyncIndicator'
import api from '../src/services/api'
import { mutationOptions } from '../src/utils/mutationProtocol'
export default function Harness() {
  const auth = useAuth(), sync = useBackgroundSync()
  useEffect(() => { window.gc007 = { auth, api, mutationOptions }; window.gc009 = { sync } }, [auth, sync])
  return <><p>{auth.isLoading ? 'Loading' : auth.user?.username || 'Signed out'}</p><SyncIndicator variant="card" /></>
}
history.replaceState(null, '', '/login')
createRoot(document.getElementById('root')).render(<BrowserRouter><LanguageProvider><AuthProvider><Harness /></AuthProvider></LanguageProvider></BrowserRouter>)
