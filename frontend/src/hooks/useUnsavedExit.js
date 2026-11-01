import { useContext } from 'react'
import { UnsavedChangesContext } from '../contexts/UnsavedChangesContext'

// Explicit sign-out clears private data before it navigates. Ask while the
// original account's form is still available; forced expiry is never blocked.
export default function useUnsavedExit() {
  return useContext(UnsavedChangesContext)?.confirmExit || (() => Promise.resolve(true))
}
