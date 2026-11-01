import { readPrivateNavigationState } from '../utils/privateNavigation'
import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

// Preserve a filtered expense view after an add/edit/save, including offline
// saves. Accept the same vehicle's expense/workshop page or an owner-bound
// statement draft handoff.
export default function useExpenseNavigation(vehicleId) {
  const navigate = useNavigate()
  const { state } = useLocation()
  const base = `/vehicles/${vehicleId}`
  const workshop = state?.workshopReturnTo === `${base}/appointments`
  const statement = readPrivateNavigationState(state)?.reconciliationReturnTo
  const reconciliation = typeof statement === 'string' && /^\/reconciliation\?batch=[1-9]\d*$/.test(statement)
  const returnTo = reconciliation ? statement : workshop ? state.workshopReturnTo : state?.expenseReturnTo
  const valid = reconciliation || workshop || typeof returnTo === 'string' && (returnTo === `${base}/expenses` || returnTo.startsWith(`${base}/expenses?`))
  return useCallback((target, options) => {
    const destination = valid && [base, `${base}/consumables`, `${base}/expenses`].includes(target) ? returnTo : target
    return options === undefined ? navigate(destination) : navigate(destination, options)
  }, [navigate, valid, base, returnTo])
}
