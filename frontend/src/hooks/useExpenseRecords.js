import { useEffect, useState } from 'react'
import { vehicleApi } from '../services/api'

export default function useExpenseRecords(vehicleId, filters, refreshKey = 0, enabled = true) {
  const { category, year, month = null, page = 1, scope = 'period' } = filters
  const key = JSON.stringify([vehicleId, category, year, month, page, scope, refreshKey, enabled])
  const [state, setState] = useState({ key: null, data: null, error: false })
  useEffect(() => {
    if (!enabled) return
    let active = true
    vehicleApi.getExpenseRecords(vehicleId, { category, year, month, page, scope })
      .then(res => { if (active) setState({ key, data: res.data, error: false }) })
      .catch(() => { if (active) setState({ key, data: null, error: true }) })
    return () => { active = false }
  }, [vehicleId, category, year, month, page, scope, refreshKey, enabled, key])
  const setRecords = update => setState(current => current.key === key && current.data
    ? { ...current, data: { ...current.data, records: typeof update === 'function' ? update(current.data.records) : update } } : current)
  return state.key === key ? { ...state, loading: false, setRecords } : { data: null, error: false, loading: enabled, setRecords }
}
