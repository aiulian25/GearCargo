import { useEffect, useState } from 'react'
import { vehicleApi } from '../services/api'

// Complete server aggregates remain independent of detail page requests.
export default function useExpenseSummary(vehicleId, year, refreshKey = '') {
  const [retry, setRetry] = useState(0)
  const key = JSON.stringify([vehicleId, year, refreshKey, retry])
  const [state, setState] = useState({ key: null, data: null, error: false })
  useEffect(() => {
    let active = true
    vehicleApi.getExpenseSummary(vehicleId, { year })
      .then(res => { if (active) setState({ key, data: res.data, error: false }) })
      .catch(() => { if (active) setState({ key, data: null, error: true }) })
    return () => { active = false }
  }, [vehicleId, year, refreshKey, retry, key])
  return { ...(state.key === key ? state : { data: null, error: false }), retry: () => setRetry(value => value + 1) }
}
