import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import api from '../src/services/api'
import { db } from '../src/db/database'
import { mutationDb, getQueueState } from '../src/db/mutationQueue'
import { workerMessage, getBoundIdentity } from '../src/utils/offlineIdentity'
import { saveExpenseWithReceipt } from '../src/utils/receiptExpense'
import { mutationOptions } from '../src/utils/mutationProtocol'
export default function Harness() {
  const auth = useAuth()
  useEffect(() => { window.gc011 = { auth, api, db, mutationDb, getQueueState, workerMessage, getBoundIdentity, saveExpenseWithReceipt, mutationOptions } }, [auth])
  return <p>{auth.isLoading ? 'Loading' : auth.user?.username || 'Signed out'}</p>
}
history.replaceState(null, '', '/login')
createRoot(document.getElementById('root')).render(<AuthProvider><Harness /></AuthProvider>)
