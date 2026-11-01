import { useMemo } from 'react'
import { DateFormatContext } from '../hooks/useDateFormat'
import { createDateFormatters } from '../utils/dateFormat'

export function DateFormatProvider({ language, dateFormat, timezone, children }) {
  const formatters = useMemo(() => createDateFormatters({ language, date_format: dateFormat, timezone }),
    [language, dateFormat, timezone])
  return <DateFormatContext.Provider value={formatters}>{children}</DateFormatContext.Provider>
}
