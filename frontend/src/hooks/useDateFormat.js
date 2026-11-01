import { createContext, useContext } from 'react'
import { createDateFormatters } from '../utils/dateFormat'

export const DateFormatContext = createContext(createDateFormatters())

export function useDateFormat() {
  return useContext(DateFormatContext)
}
