// Browser-only test harness using the real AuthProvider and Axios pipeline.
// Bundled independently by queueIdentity.mjs; never included in the app build.
import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import api from '../src/services/api'

function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc007 = { auth, api } }, [auth])
  return <p>{auth.isLoading ? 'Loading' : auth.user?.username || 'Signed out'}</p>
}

history.replaceState(null, '', '/login')
createRoot(document.getElementById('root')).render(<AuthProvider><Harness /></AuthProvider>)
