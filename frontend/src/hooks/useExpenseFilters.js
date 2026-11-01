import { useSearchParams } from 'react-router-dom'

export const EXPENSE_TABS = ['fuel', 'service', 'repair', 'tax', 'parking', 'consumable', 'insurance', 'todo', 'reminder']
const integer = (value, fallback, min, max) => /^\d+$/.test(value || '') && Number(value) >= min && Number(value) <= max ? Number(value) : fallback

export function expensePath(vehicleId, filters = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value != null) params.set(key, String(value))
  return `/vehicles/${vehicleId}/expenses${params.size ? `?${params}` : ''}`
}

export default function useExpenseFilters() {
  const [params, setParams] = useSearchParams()
  const year = integer(params.get('year'), new Date().getFullYear(), 1, 9999)
  const month = integer(params.get('month'), null, 1, 12)
  const page = integer(params.get('page'), 1, 1, 2147483647)
  const tab = EXPENSE_TABS.includes(params.get('tab')) ? params.get('tab') : 'fuel'
  const update = (values, replace = false) => setParams(previous => {
    const next = new URLSearchParams(previous)
    for (const [key, value] of Object.entries(values)) {
      if (value == null) next.delete(key)
      else next.set(key, String(value))
    }
    return next
  }, { replace })
  return { year, month, page, tab,
    setYear: value => update({ year: value, month: null, page: null }),
    setMonth: value => update({ month: value, page: null }),
    setTab: value => update({ tab: value, page: null }),
    setPage: (value, replace = false) => update({ page: value }, replace),
  }
}
